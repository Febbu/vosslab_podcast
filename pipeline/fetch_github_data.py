#!/usr/bin/env python3
import argparse
import json
import os
import re
from datetime import datetime
from datetime import timedelta
from datetime import timezone

import github_client
import pipeline_settings


DATE_HEADING_RE = re.compile(r"^##\s+(\d{4}-\d{2}-\d{2})\b")


#============================================
def log_step(message: str) -> None:
	"""
	Print one timestamped progress line.
	"""
	now_text = datetime.now().strftime("%H:%M:%S")
	print(f"[fetch_github_data {now_text}] {message}", flush=True)


#============================================
def parse_args() -> argparse.Namespace:
	"""
	Parse command-line arguments.
	"""
	parser = argparse.ArgumentParser(
		description="Fetch weekly GitHub data and write JSONL records."
	)
	parser.add_argument(
		"--user",
		default="",
		help="GitHub username to fetch (falls back to settings.yaml then vosslab).",
	)
	parser.add_argument(
		"--settings",
		default="settings.yaml",
		help="YAML settings path for defaults.",
	)
	parser.add_argument(
		"--last-days",
		dest="last_n_days",
		type=int,
		default=1,
		help="Fetch activity from the last N days (default: 1).",
	)
	parser.add_argument(
		"--output",
		default="out/github_data.jsonl",
		help="Path to JSONL output file.",
	)
	parser.add_argument(
		"--include-forks",
		action="store_true",
		help="Include forked repos in fetch results.",
	)
	parser.add_argument(
		"--max-repos",
		type=int,
		default=0,
		help="Optional cap for repos processed (0 means no cap).",
	)
	parser.add_argument(
		"--skip-changelog",
		action="store_true",
		help="Skip fetching docs/CHANGELOG.md records for relevant repos.",
	)
	parser.add_argument(
		"--daily-cache-dir",
		default="out/daily_cache",
		help="Directory for per-day JSONL cache files.",
	)
	args = parser.parse_args()
	return args


#============================================
def resolve_window_days(args: argparse.Namespace) -> int:
	"""
	Resolve selected trailing day window.
	"""
	if args.last_n_days < 1:
		raise RuntimeError("--last-days must be >= 1")
	return args.last_n_days


#============================================
def utc_now() -> datetime:
	"""
	Return UTC now as a timezone-aware datetime.
	"""
	now = datetime.now(timezone.utc)
	return now


#============================================
def parse_iso(ts: str) -> datetime:
	"""
	Parse an ISO timestamp string into a timezone-aware datetime.
	"""
	if not ts:
		return datetime(1970, 1, 1, tzinfo=timezone.utc)
	parsed = datetime.fromisoformat(ts.replace("Z", "+00:00"))
	return parsed


#============================================
def in_window(ts: str, window_start: datetime, window_end: datetime) -> bool:
	"""
	Check if timestamp falls inside the active window.
	"""
	if not ts:
		return False
	event_time = parse_iso(ts)
	return window_start <= event_time <= window_end


#============================================
def to_utc_iso(value) -> str:
	"""
	Convert datetime-like values to ISO-8601 UTC strings.
	"""
	if value is None:
		return ""
	if isinstance(value, str):
		return value
	if isinstance(value, datetime):
		if value.tzinfo is None:
			value = value.replace(tzinfo=timezone.utc)
		return value.astimezone(timezone.utc).isoformat()
	return str(value)


#============================================
def repo_to_dict(repo_obj) -> dict:
	"""
	Normalize a PyGithub repository object to REST-like dict shape.
	"""
	data = getattr(repo_obj, "raw_data", {}) or {}
	repo = dict(data)
	if "full_name" not in repo:
		repo["full_name"] = getattr(repo_obj, "full_name", "")
	if "name" not in repo:
		repo["name"] = getattr(repo_obj, "name", "")
	if "fork" not in repo:
		repo["fork"] = bool(getattr(repo_obj, "fork", False))
	if "created_at" not in repo:
		repo["created_at"] = to_utc_iso(getattr(repo_obj, "created_at", None))
	if "updated_at" not in repo:
		repo["updated_at"] = to_utc_iso(getattr(repo_obj, "updated_at", None))
	if "pushed_at" not in repo:
		repo["pushed_at"] = to_utc_iso(getattr(repo_obj, "pushed_at", None))
	if "default_branch" not in repo:
		repo["default_branch"] = getattr(repo_obj, "default_branch", "")
	return repo


#============================================
def commit_to_dict(commit_obj) -> dict:
	"""
	Normalize a PyGithub commit object to REST-like dict shape.
	"""
	data = getattr(commit_obj, "raw_data", {}) or {}
	commit = dict(data)
	if "sha" not in commit:
		commit["sha"] = getattr(commit_obj, "sha", "")
	commit_payload = commit.get("commit") or {}
	if "commit" not in commit:
		commit_payload = {}
		commit["commit"] = commit_payload
	author_payload = commit_payload.get("author") or {}
	if "author" not in commit_payload:
		author_payload = {}
		commit_payload["author"] = author_payload
	committer_payload = commit_payload.get("committer") or {}
	if "committer" not in commit_payload:
		committer_payload = {}
		commit_payload["committer"] = committer_payload
	if not author_payload.get("date"):
		author_payload["date"] = to_utc_iso(getattr(commit_obj.commit.author, "date", None))
	if not committer_payload.get("date"):
		committer_payload["date"] = to_utc_iso(getattr(commit_obj.commit.committer, "date", None))
	if not commit_payload.get("message"):
		commit_payload["message"] = getattr(commit_obj.commit, "message", "")
	return commit


#============================================
def issue_to_dict(issue_obj) -> dict:
	"""
	Normalize a PyGithub issue object to REST-like dict shape.
	"""
	data = getattr(issue_obj, "raw_data", {}) or {}
	issue = dict(data)
	if "number" not in issue:
		issue["number"] = getattr(issue_obj, "number", 0)
	if "title" not in issue:
		issue["title"] = getattr(issue_obj, "title", "")
	if "state" not in issue:
		issue["state"] = getattr(issue_obj, "state", "")
	if "updated_at" not in issue:
		issue["updated_at"] = to_utc_iso(getattr(issue_obj, "updated_at", None))
	if "created_at" not in issue:
		issue["created_at"] = to_utc_iso(getattr(issue_obj, "created_at", None))
	pr_attr = getattr(issue_obj, "pull_request", None)
	if ("pull_request" not in issue) and (pr_attr is not None):
		issue["pull_request"] = {}
	return issue


#============================================
def write_jsonl_line(handle, record: dict) -> None:
	"""
	Write one JSONL record.
	"""
	handle.write(json.dumps(record, sort_keys=True))
	handle.write("\n")


#============================================
def parse_latest_changelog_entry(changelog_text: str) -> tuple[str, str, str]:
	"""
	Extract the latest dated changelog heading and section text.
	"""
	if not changelog_text.strip():
		return "", "", ""
	lines = changelog_text.splitlines()
	heading_index = -1
	heading_value = ""
	heading_date = ""
	for index, line in enumerate(lines):
		match = DATE_HEADING_RE.match(line.strip())
		if match:
			heading_index = index
			heading_value = line.strip()
			heading_date = match.group(1)
			break
	if heading_index < 0:
		return "", "", ""
	entry_lines = [heading_value]
	for line in lines[heading_index + 1:]:
		if line.strip().startswith("## "):
			break
		entry_lines.append(line.rstrip())
	entry_text = "\n".join(entry_lines).strip()
	return heading_value, heading_date, entry_text


#============================================
def fetch_repo_changelog_content(
	client: github_client.GitHubClient,
	repo_obj,
	ref_name: str,
) -> dict:
	"""
	Fetch docs/CHANGELOG.md metadata and text from one repository.
	"""
	payload = client.get_file_content(repo_obj, "docs/CHANGELOG.md", ref_name)
	if payload is None:
		return {}
	result = {
		"path": payload.get("path") or "docs/CHANGELOG.md",
		"sha": payload.get("sha") or "",
		"size": payload.get("size") or 0,
		"changelog_text": payload.get("text") or "",
	}
	return result


#============================================
def build_changelog_record(
	user: str,
	window_start: datetime,
	window_end: datetime,
	repo_full_name: str,
	repo_name: str,
	changelog_info: dict,
) -> dict:
	"""
	Build one normalized changelog record.
	"""
	changelog_text = changelog_info.get("changelog_text") or ""
	heading, heading_date, entry_text = parse_latest_changelog_entry(changelog_text)
	event_time = window_end.isoformat()
	if heading_date:
		event_time = f"{heading_date}T00:00:00+00:00"
	record = {
		"record_type": "repo_changelog",
		"user": user,
		"window_start": window_start.isoformat(),
		"window_end": window_end.isoformat(),
		"event_time": event_time,
		"repo_full_name": repo_full_name,
		"repo_name": repo_name,
		"path": changelog_info.get("path") or "docs/CHANGELOG.md",
		"sha": changelog_info.get("sha") or "",
		"size": changelog_info.get("size") or 0,
		"latest_heading": heading,
		"latest_entry": entry_text,
	}
	return record


#============================================
def build_repo_record(
	user: str,
	window_start: datetime,
	window_end: datetime,
	repo: dict,
) -> dict:
	"""
	Build one normalized repo metadata record.
	"""
	record = {
		"record_type": "repo",
		"user": user,
		"window_start": window_start.isoformat(),
		"window_end": window_end.isoformat(),
		"event_time": repo.get("pushed_at") or repo.get("created_at"),
		"repo_full_name": repo.get("full_name"),
		"repo_name": repo.get("name"),
		"data": repo,
	}
	return record


#============================================
def build_commit_record(
	user: str,
	window_start: datetime,
	window_end: datetime,
	repo_full_name: str,
	repo_name: str,
	commit: dict,
) -> dict:
	"""
	Build one normalized commit record.
	"""
	commit_data = commit.get("commit") or {}
	author_data = commit_data.get("author") or {}
	committer_data = commit_data.get("committer") or {}
	event_time = author_data.get("date") or committer_data.get("date")
	record = {
		"record_type": "commit",
		"user": user,
		"window_start": window_start.isoformat(),
		"window_end": window_end.isoformat(),
		"event_time": event_time,
		"repo_full_name": repo_full_name,
		"repo_name": repo_name,
		"sha": commit.get("sha"),
		"message": commit_data.get("message"),
		"data": commit,
	}
	return record


#============================================
def build_issue_record(
	user: str,
	window_start: datetime,
	window_end: datetime,
	repo_full_name: str,
	repo_name: str,
	issue: dict,
) -> dict:
	"""
	Build one normalized issue or pull-request record.
	"""
	record_type = "issue"
	if "pull_request" in issue:
		record_type = "pull_request"
	record = {
		"record_type": record_type,
		"user": user,
		"window_start": window_start.isoformat(),
		"window_end": window_end.isoformat(),
		"event_time": issue.get("updated_at") or issue.get("created_at"),
		"repo_full_name": repo_full_name,
		"repo_name": repo_name,
		"number": issue.get("number"),
		"title": issue.get("title"),
		"state": issue.get("state"),
		"data": issue,
	}
	return record


#============================================
def timestamp_to_day_key(ts: str, fallback_day: str) -> str:
	"""
	Resolve YYYY-MM-DD key from timestamp text.
	"""
	if ts and len(ts) >= 10 and ts[4] == "-" and ts[7] == "-":
		return ts[:10]
	return fallback_day


#============================================
def build_window_day_keys(window_end: datetime, window_days: int) -> list[str]:
	"""
	Build ordered per-day keys for cache output.
	"""
	keys = []
	for offset in range(window_days - 1, -1, -1):
		day_key = (window_end - timedelta(days=offset)).date().isoformat()
		keys.append(day_key)
	return keys


#============================================
def add_record_to_daily_bucket(
	daily_buckets: dict[str, list[dict]],
	record: dict,
	fallback_day: str,
) -> str:
	"""
	Add one record to its day-bucket list.
	"""
	day_key = timestamp_to_day_key(record.get("event_time", ""), fallback_day)
	if day_key not in daily_buckets:
		daily_buckets[day_key] = []
	daily_buckets[day_key].append(record)
	return day_key


#============================================
def count_record_types(records: list[dict]) -> dict[str, int]:
	"""
	Count record types in one record list.
	"""
	counts: dict[str, int] = {}
	for record in records:
		record_type = record.get("record_type") or "unknown"
		if record_type not in counts:
			counts[record_type] = 0
		counts[record_type] += 1
	return counts


#============================================
def write_daily_cache_files(
	cache_dir: str,
	user: str,
	window_start: datetime,
	window_end: datetime,
	day_keys: list[str],
	daily_buckets: dict[str, list[dict]],
) -> list[str]:
	"""
	Write one JSONL file per day for caching.
	"""
	cache_path = os.path.abspath(cache_dir)
	os.makedirs(cache_path, exist_ok=True)
	written_files = []
	for day_key in day_keys:
		records = daily_buckets.get(day_key, [])
		day_file = os.path.join(cache_path, f"github_data_{day_key}.jsonl")
		with open(day_file, "w", encoding="utf-8") as handle:
			start_record = {
				"record_type": "daily_metadata",
				"user": user,
				"day": day_key,
				"window_start": window_start.isoformat(),
				"window_end": window_end.isoformat(),
			}
			write_jsonl_line(handle, start_record)
			for record in records:
				write_jsonl_line(handle, record)
			summary_record = {
				"record_type": "daily_summary",
				"user": user,
				"day": day_key,
				"record_counts": count_record_types(records),
				"total_records": len(records),
			}
			write_jsonl_line(handle, summary_record)
		written_files.append(day_file)
	return written_files


#============================================
def main() -> None:
	"""
	Run the weekly GitHub fetch and write JSONL output.
	"""
	args = parse_args()
	settings, settings_path = pipeline_settings.load_settings(args.settings)
	default_user = pipeline_settings.get_setting_str(settings, ["github", "username"], "")
	user = args.user.strip() or default_user or "vosslab"
	log_step(f"Using settings file: {settings_path}")
	log_step(f"Using GitHub user: {user}")
	window_days = resolve_window_days(args)
	window_end = utc_now()
	window_start = window_end - timedelta(days=window_days)
	fallback_day = window_end.date().isoformat()
	log_step(
		f"Active window: {window_start.isoformat()} -> {window_end.isoformat()} "
		+ f"({window_days} day(s))"
	)

	token = pipeline_settings.get_setting_str(settings, ["github", "token"], "")
	if token:
		log_step("Using authenticated GitHub API mode via settings.yaml github.token.")
	else:
		log_step("Using unauthenticated GitHub API mode (lower rate limit).")

	try:
		client = github_client.GitHubClient(token, log_fn=log_step)
	except RuntimeError as error:
		log_step(str(error))
		log_step("Aborting fetch run before network calls.")
		return
	stopped_due_to_rate_limit = False
	stopped_reason = ""
	log_step("Fetching repository list.")
	repos = []
	try:
		repo_iter = client.list_repos(user)
		if args.max_repos > 0:
			for repo_obj in repo_iter:
				repos.append(repo_obj)
				if len(repos) >= args.max_repos:
					break
		else:
			repos = list(repo_iter)
	except github_client.RateLimitError as error:
		stopped_due_to_rate_limit = True
		stopped_reason = str(error)
		log_step(stopped_reason)
		log_step("Repository listing stopped by rate limit; writing summary-only output.")
	if args.max_repos > 0:
		log_step(f"Applied --max-repos cap: {len(repos)} repo(s).")
	else:
		log_step(f"Repository candidates: {len(repos)}.")

	output_path = os.path.abspath(args.output)
	output_dir = os.path.dirname(output_path)
	os.makedirs(output_dir, exist_ok=True)
	log_step(f"Writing JSONL output to: {output_path}")

	record_counts = {
		"repo": 0,
		"commit": 0,
		"issue": 0,
		"pull_request": 0,
		"repo_changelog": 0,
	}
	daily_buckets: dict[str, list[dict]] = {}
	day_keys = build_window_day_keys(window_end, window_days)

	with open(output_path, "w", encoding="utf-8") as handle:
		start_record = {
			"record_type": "run_metadata",
			"user": user,
			"window_start": window_start.isoformat(),
			"window_end": window_end.isoformat(),
			"window_days": window_days,
			"fetched_at": window_end.isoformat(),
			"source": "fetch_github_data.py",
			"daily_cache_dir": os.path.abspath(args.daily_cache_dir),
		}
		write_jsonl_line(handle, start_record)

		for repo_obj in repos:
			repo = repo_to_dict(repo_obj)
			if repo.get("fork") and not args.include_forks:
				log_step(f"Skipping fork repo: {repo.get('full_name') or '(unknown)'}")
				continue
			repo_full_name = repo.get("full_name") or ""
			repo_name = repo.get("name") or ""
			if not repo_full_name:
				continue
			log_step(f"Processing repo: {repo_full_name}")

			repo_record = build_repo_record(
				user,
				window_start,
				window_end,
				repo,
			)
			write_jsonl_line(handle, repo_record)
			add_record_to_daily_bucket(daily_buckets, repo_record, fallback_day)
			record_counts["repo"] += 1

			updated_marker = (
				repo.get("updated_at")
				or repo.get("pushed_at")
				or repo.get("created_at")
				or ""
			)
			repo_recent = in_window(
				updated_marker,
				window_start,
				window_end,
			)
			if not repo_recent:
				log_step(
					f"Skipping detail fetch for stale repo: {repo_full_name} "
					+ f"(updated marker: {updated_marker or 'none'})"
				)
				continue
			repo_activity_count = 0
			repo_commit_count = 0
			repo_issue_count = 0
			repo_pull_request_count = 0

			try:
				commits = client.list_commits(repo_obj, window_start, window_end)
			except github_client.RateLimitError as error:
				stopped_due_to_rate_limit = True
				stopped_reason = str(error)
				log_step(stopped_reason)
				log_step("Stopping further repo detail fetches and writing partial output.")
				break
			for commit_obj in commits:
				commit = commit_to_dict(commit_obj)
				commit_record = build_commit_record(
					user,
					window_start,
					window_end,
					repo_full_name,
					repo_name,
					commit,
				)
				write_jsonl_line(handle, commit_record)
				add_record_to_daily_bucket(daily_buckets, commit_record, fallback_day)
				record_counts["commit"] += 1
				repo_activity_count += 1
				repo_commit_count += 1
			log_step(f"Repo {repo_full_name}: collected {repo_commit_count} commit record(s).")

			try:
				issues = client.list_issues(repo_obj, window_start)
			except github_client.RateLimitError as error:
				stopped_due_to_rate_limit = True
				stopped_reason = str(error)
				log_step(stopped_reason)
				log_step("Stopping further repo detail fetches and writing partial output.")
				break
			for issue_obj in issues:
				issue = issue_to_dict(issue_obj)
				event_time = issue.get("updated_at") or issue.get("created_at") or ""
				event_dt = parse_iso(event_time)
				if event_dt < window_start:
					continue
				issue_record = build_issue_record(
					user,
					window_start,
					window_end,
					repo_full_name,
					repo_name,
					issue,
				)
				write_jsonl_line(handle, issue_record)
				add_record_to_daily_bucket(daily_buckets, issue_record, fallback_day)
				record_type = issue_record["record_type"]
				record_counts[record_type] += 1
				repo_activity_count += 1
				if record_type == "pull_request":
					repo_pull_request_count += 1
				else:
					repo_issue_count += 1
			log_step(
				f"Repo {repo_full_name}: collected {repo_issue_count} issue record(s) and "
				+ f"{repo_pull_request_count} pull request record(s)."
			)

			if (not args.skip_changelog) and (repo_recent or repo_activity_count > 0):
				ref_name = repo.get("default_branch") or ""
				try:
					changelog_info = fetch_repo_changelog_content(
						client,
						repo_obj,
						ref_name,
					)
				except github_client.RateLimitError as error:
					stopped_due_to_rate_limit = True
					stopped_reason = str(error)
					log_step(stopped_reason)
					log_step("Stopping further repo detail fetches and writing partial output.")
					break
				if changelog_info:
					changelog_record = build_changelog_record(
						user,
						window_start,
						window_end,
						repo_full_name,
						repo_name,
						changelog_info,
					)
					write_jsonl_line(handle, changelog_record)
					add_record_to_daily_bucket(daily_buckets, changelog_record, fallback_day)
					record_counts["repo_changelog"] += 1

		end_record = {
			"record_type": "run_summary",
			"user": user,
			"window_start": window_start.isoformat(),
			"window_end": window_end.isoformat(),
			"window_days": window_days,
			"fetched_at": utc_now().isoformat(),
			"record_counts": record_counts,
			"daily_cache_dir": os.path.abspath(args.daily_cache_dir),
			"stopped_due_to_rate_limit": stopped_due_to_rate_limit,
			"stop_reason": stopped_reason,
		}
		write_jsonl_line(handle, end_record)

	written_daily_files = write_daily_cache_files(
		args.daily_cache_dir,
		user,
		window_start,
		window_end,
		day_keys,
		daily_buckets,
	)
	total_records = (
		record_counts["repo"]
		+ record_counts["commit"]
		+ record_counts["issue"]
		+ record_counts["pull_request"]
		+ record_counts["repo_changelog"]
		+ 2
	)
	log_step(f"Wrote {output_path} ({total_records} records)")
	log_step(
		"Daily cache files written: "
		+ f"{len(written_daily_files)} in {os.path.abspath(args.daily_cache_dir)}"
	)
	if stopped_due_to_rate_limit:
		log_step("Run finished with partial data due to GitHub API rate limiting.")


if __name__ == "__main__":
	main()
