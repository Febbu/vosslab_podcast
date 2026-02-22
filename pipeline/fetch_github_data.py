#!/usr/bin/env python3
import argparse
import base64
import json
import os
import random
import re
import time
from datetime import datetime
from datetime import timedelta
from datetime import timezone

import requests

import pipeline_settings


PER_PAGE = 100
DATE_HEADING_RE = re.compile(r"^##\s+(\d{4}-\d{2}-\d{2})\b")


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
	window_group = parser.add_mutually_exclusive_group()
	window_group.add_argument(
		"--last-day",
		action="store_true",
		help="Use a 1-day window (default when no window flag is provided).",
	)
	window_group.add_argument(
		"--last-two-days",
		action="store_true",
		help="Use a 2-day window.",
	)
	window_group.add_argument(
		"--last-week",
		action="store_true",
		help="Use a 7-day window.",
	)
	window_group.add_argument(
		"--last-month",
		action="store_true",
		help="Use a 30-day window.",
	)
	window_group.add_argument(
		"--window-days",
		type=int,
		default=None,
		help="Use a custom day window size.",
	)
	parser.add_argument(
		"--output",
		default="out/github_data.jsonl",
		help="Path to JSONL output file.",
	)
	parser.add_argument(
		"--token",
		default="",
		help="Optional GitHub token. Falls back to GH_TOKEN or GITHUB_TOKEN.",
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
		"--api-base",
		default="https://api.github.com",
		help="GitHub API base URL.",
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
	Resolve selected window-day setting from exclusive options.
	"""
	if args.last_two_days:
		return 2
	if args.last_week:
		return 7
	if args.last_month:
		return 30
	if args.window_days is not None:
		if args.window_days < 1:
			raise RuntimeError("--window-days must be >= 1")
		return args.window_days
	# --last-day is treated as explicit, and default also falls back to one day.
	return 1


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
def build_headers(token: str) -> dict[str, str]:
	"""
	Build GitHub request headers.
	"""
	headers = {
		"Accept": "application/vnd.github+json",
	}
	if token:
		headers["Authorization"] = f"Bearer {token}"
	return headers


#============================================
def github_get_json(
	url: str,
	params: dict[str, str | int],
	headers: dict[str, str],
) -> list[dict] | dict:
	"""
	Send one API request with light randomized spacing.
	"""
	time.sleep(random.random())
	response = requests.get(
		url,
		headers=headers,
		params=params,
		timeout=45,
	)
	response.raise_for_status()
	payload = response.json()
	return payload


#============================================
def fetch_paginated(
	url: str,
	base_params: dict[str, str | int],
	headers: dict[str, str],
) -> list[dict]:
	"""
	Fetch all paginated list results from one endpoint.
	"""
	page = 1
	results: list[dict] = []
	while True:
		params = dict(base_params)
		params["per_page"] = PER_PAGE
		params["page"] = page
		payload = github_get_json(url, params, headers)
		if not isinstance(payload, list):
			raise RuntimeError(f"Expected list payload from {url}")
		if not payload:
			break
		results.extend(payload)
		if len(payload) < PER_PAGE:
			break
		page += 1
	return results


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
	api_base: str,
	repo_full_name: str,
	ref_name: str,
	headers: dict[str, str],
) -> dict:
	"""
	Fetch docs/CHANGELOG.md metadata and text from one repository.
	"""
	url = f"{api_base}/repos/{repo_full_name}/contents/docs/CHANGELOG.md"
	params = {}
	if ref_name:
		params["ref"] = ref_name
	time.sleep(random.random())
	response = requests.get(
		url,
		headers=headers,
		params=params,
		timeout=45,
	)
	if response.status_code == 404:
		return {}
	if response.status_code == 403:
		return {}
	response.raise_for_status()
	payload = response.json()
	if not isinstance(payload, dict):
		return {}
	if payload.get("type") != "file":
		return {}
	content_encoded = payload.get("content") or ""
	encoding = payload.get("encoding") or ""
	if encoding != "base64":
		return {}
	content_clean = content_encoded.replace("\n", "")
	try:
		content_bytes = base64.b64decode(content_clean, validate=False)
	except Exception:
		return {}
	changelog_text = content_bytes.decode("utf-8", errors="replace")
	result = {
		"path": payload.get("path") or "docs/CHANGELOG.md",
		"sha": payload.get("sha") or "",
		"size": payload.get("size") or 0,
		"changelog_text": changelog_text,
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
	print(f"Using settings file: {settings_path}")
	print(f"Using GitHub user: {user}")
	window_days = resolve_window_days(args)
	window_end = utc_now()
	window_start = window_end - timedelta(days=window_days)
	fallback_day = window_end.date().isoformat()

	token = args.token.strip()
	if not token:
		token = os.environ.get("GH_TOKEN", "").strip()
	if not token:
		token = os.environ.get("GITHUB_TOKEN", "").strip()

	api_base = args.api_base.rstrip("/")
	headers = build_headers(token)

	repos_url = f"{api_base}/users/{user}/repos"
	repo_params = {
		"type": "owner",
		"sort": "updated",
		"direction": "desc",
	}
	repos = fetch_paginated(repos_url, repo_params, headers)
	if args.max_repos > 0:
		repos = repos[:args.max_repos]

	output_path = os.path.abspath(args.output)
	output_dir = os.path.dirname(output_path)
	os.makedirs(output_dir, exist_ok=True)

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

		for repo in repos:
			if repo.get("fork") and not args.include_forks:
				continue
			repo_full_name = repo.get("full_name") or ""
			repo_name = repo.get("name") or ""
			if not repo_full_name:
				continue

			repo_record = build_repo_record(
				user,
				window_start,
				window_end,
				repo,
			)
			write_jsonl_line(handle, repo_record)
			add_record_to_daily_bucket(daily_buckets, repo_record, fallback_day)
			record_counts["repo"] += 1
			repo_recent = in_window(
				repo.get("pushed_at") or repo.get("created_at") or "",
				window_start,
				window_end,
			)
			repo_activity_count = 0

			commit_url = f"{api_base}/repos/{repo_full_name}/commits"
			commit_params = {
				"since": window_start.isoformat(),
				"until": window_end.isoformat(),
			}
			commits = fetch_paginated(commit_url, commit_params, headers)
			for commit in commits:
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

			issues_url = f"{api_base}/repos/{repo_full_name}/issues"
			issue_params = {
				"state": "all",
				"since": window_start.isoformat(),
				"sort": "updated",
				"direction": "desc",
			}
			issues = fetch_paginated(issues_url, issue_params, headers)
			for issue in issues:
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

			if (not args.skip_changelog) and (repo_recent or repo_activity_count > 0):
				ref_name = repo.get("default_branch") or ""
				changelog_info = fetch_repo_changelog_content(
					api_base,
					repo_full_name,
					ref_name,
					headers,
				)
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
	print(f"Wrote {output_path} ({total_records} records)")
	print(f"Wrote {len(written_daily_files)} daily cache file(s) in {os.path.abspath(args.daily_cache_dir)}")


if __name__ == "__main__":
	main()
