#!/usr/bin/env python3
import argparse
import json
import os
import re
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from zoneinfo import ZoneInfo
from zoneinfo import ZoneInfoNotFoundError

from podlib import github_client
from podlib import pipeline_settings

try:
	import rich.console
except ModuleNotFoundError:
	rich = None


DATE_HEADING_RE = re.compile(r"^##\s+(\d{4}-\d{2}-\d{2})\b")
DATE_STAMP_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
REPO_LIST_CACHE_TTL_SECONDS = 24 * 60 * 60
DAY_RESET_HOUR_LOCAL = 5
DEFAULT_DAY_RESET_TIMEZONE = "America/Chicago"
RICH_CONSOLE = rich.console.Console() if rich is not None else None


#============================================
def log_step(message: str) -> None:
	"""
	Print one timestamped progress line.
	"""
	now_text = datetime.now().strftime("%H:%M:%S")
	line = f"[fetch_github_data {now_text}] {message}"
	if RICH_CONSOLE is None:
		print(line, flush=True)
		return
	lower = message.lower()
	style = "cyan"
	if ("failed" in lower) or ("error" in lower):
		style = "bold red"
	elif ("rate limit" in lower) or ("skipping" in lower):
		style = "yellow"
	elif ("wrote " in lower) or ("collected" in lower):
		style = "green"
	RICH_CONSOLE.print(line, style=style)


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
		help="Fetch activity from the last 1 day (default).",
	)
	window_group.add_argument(
		"--last-week",
		action="store_true",
		help="Fetch activity from the last 7 days.",
	)
	window_group.add_argument(
		"--last-month",
		action="store_true",
		help="Fetch activity from the last 30 days.",
	)
	parser.add_argument(
		"--output",
		default="out/github_data.jsonl",
		help="Path to JSONL output file.",
	)
	fork_group = parser.add_mutually_exclusive_group()
	fork_group.add_argument(
		"--include-forks",
		dest="include_forks",
		action="store_true",
		help="Include forked repos in fetch results (default).",
	)
	fork_group.add_argument(
		"--no-include-forks",
		dest="include_forks",
		action="store_false",
		help="Exclude forked repos from fetch results.",
	)
	parser.set_defaults(include_forks=True)
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
	if args.last_month:
		return 30
	if args.last_week:
		return 7
	return 1


#============================================
def local_date_stamp() -> str:
	"""
	Return local date stamp for output filenames.
	"""
	return datetime.now().astimezone().strftime("%Y-%m-%d")


#============================================
def resolve_day_reset_timezone_name() -> str:
	"""
	Resolve reset-timezone name from TZ env with Chicago default.
	"""
	value = (os.environ.get("TZ", "") or "").strip()
	if value:
		return value
	return DEFAULT_DAY_RESET_TIMEZONE


#============================================
def resolve_day_reset_timezone() -> ZoneInfo:
	"""
	Resolve reset-timezone object from TZ env with safe fallback.
	"""
	name = resolve_day_reset_timezone_name()
	try:
		return ZoneInfo(name)
	except ZoneInfoNotFoundError:
		return ZoneInfo(DEFAULT_DAY_RESET_TIMEZONE)


#============================================
def compute_completed_window_local(
	window_days: int,
	now_local: datetime,
	day_reset_hour_local: int = DAY_RESET_HOUR_LOCAL,
) -> tuple[datetime, datetime]:
	"""
	Compute last completed local window boundaries at a fixed reset hour.
	"""
	if window_days < 1:
		raise RuntimeError("window days must be >= 1")
	if now_local.tzinfo is None:
		raise RuntimeError("now_local must be timezone-aware")
	reset_today = now_local.replace(
		hour=day_reset_hour_local,
		minute=0,
		second=0,
		microsecond=0,
	)
	if now_local < reset_today:
		window_end_local = reset_today - timedelta(days=1)
	else:
		window_end_local = reset_today
	window_start_local = window_end_local - timedelta(days=window_days)
	return window_start_local, window_end_local


#============================================
def compute_completed_window_utc(
	window_days: int,
	now_utc: datetime | None = None,
	day_reset_hour_local: int = DAY_RESET_HOUR_LOCAL,
	reset_tz: ZoneInfo | None = None,
) -> tuple[datetime, datetime]:
	"""
	Compute last completed day-window in UTC using reset timezone boundaries.
	"""
	value = now_utc or utc_now()
	if value.tzinfo is None:
		value = value.replace(tzinfo=timezone.utc)
	tz_value = reset_tz or resolve_day_reset_timezone()
	now_local = value.astimezone(tz_value)
	window_start_local, window_end_local = compute_completed_window_local(
		window_days,
		now_local,
		day_reset_hour_local=day_reset_hour_local,
	)
	return (
		window_start_local.astimezone(timezone.utc),
		window_end_local.astimezone(timezone.utc),
	)


#============================================
def date_stamp_output_path(output_path: str, date_text: str) -> str:
	"""
	Ensure output filename includes one local-date stamp.
	"""
	candidate = (output_path or "").strip() or "out/github_data.jsonl"
	candidate = candidate.replace("{date}", date_text)
	directory, filename = os.path.split(candidate)
	if not filename:
		filename = "github_data.jsonl"
	stem, extension = os.path.splitext(filename)
	if not extension:
		extension = ".jsonl"
	if DATE_STAMP_RE.search(filename):
		dated_filename = filename
	else:
		dated_filename = f"{stem}_{date_text}{extension}"
	return os.path.join(directory, dated_filename)


#============================================
def repo_list_cache_path(user: str) -> str:
	"""
	Build cache path for one user's list_repos payload.
	"""
	return os.path.abspath(
		pipeline_settings.resolve_user_scoped_out_path(
			os.path.join("out", "cache", "list_repos.json"),
			os.path.join("out", "cache", "list_repos.json"),
			user,
		)
	)


#============================================
def load_repo_list_cache(
	user: str,
	now_utc: datetime,
	max_age_seconds: int | None = REPO_LIST_CACHE_TTL_SECONDS,
) -> list[dict]:
	"""
	Load cached repos when cache age is within max age.
	"""
	cache_path = repo_list_cache_path(user)
	if not os.path.isfile(cache_path):
		return []
	try:
		with open(cache_path, "r", encoding="utf-8") as handle:
			payload = json.load(handle)
	except Exception:
		return []
	if not isinstance(payload, dict):
		return []
	fetched_at_text = str(payload.get("fetched_at", "")).strip()
	if not fetched_at_text:
		return []
	try:
		fetched_at = parse_iso(fetched_at_text)
	except Exception:
		return []
	age_seconds = (now_utc - fetched_at).total_seconds()
	if age_seconds < 0:
		return []
	if (max_age_seconds is not None) and (age_seconds > max_age_seconds):
		return []
	repos = payload.get("repos")
	if not isinstance(repos, list):
		return []
	valid_repos = []
	for item in repos:
		if isinstance(item, dict):
			valid_repos.append(item)
	return valid_repos


#============================================
def save_repo_list_cache(user: str, now_utc: datetime, repos: list[dict]) -> str:
	"""
	Save list_repos payload to cache for reuse within TTL.
	"""
	cache_path = repo_list_cache_path(user)
	cache_dir = os.path.dirname(cache_path)
	if cache_dir:
		os.makedirs(cache_dir, exist_ok=True)
	payload = {
		"user": user,
		"fetched_at": now_utc.isoformat(),
		"repos": repos,
	}
	with open(cache_path, "w", encoding="utf-8") as handle:
		json.dump(payload, handle, ensure_ascii=True, sort_keys=True, indent=2)
		handle.write("\n")
	return cache_path


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
	if parsed.tzinfo is None:
		parsed = parsed.replace(tzinfo=timezone.utc)
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
	if isinstance(repo_obj, dict):
		return dict(repo_obj)
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
	if isinstance(commit_obj, dict):
		return dict(commit_obj)
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
	if isinstance(issue_obj, dict):
		return dict(issue_obj)
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
	repo_full_name: str,
	ref_name: str,
) -> dict:
	"""
	Fetch docs/CHANGELOG.md metadata and text from one repository.
	"""
	payload = client.get_file_content(repo_full_name, "docs/CHANGELOG.md", ref_name)
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
def timestamp_to_day_key(
	ts: str,
	fallback_day: str,
	day_reset_hour_local: int = DAY_RESET_HOUR_LOCAL,
	reset_tz: ZoneInfo | None = None,
) -> str:
	"""
	Resolve logical YYYY-MM-DD key from timestamp text using reset timezone hour.
	"""
	try:
		tz_value = reset_tz or resolve_day_reset_timezone()
		event_local = parse_iso(ts).astimezone(tz_value)
	except Exception:
		return fallback_day
	shifted = event_local - timedelta(hours=day_reset_hour_local)
	return shifted.date().isoformat()


#============================================
def build_window_day_keys(
	window_start: datetime,
	window_days: int,
	reset_tz: ZoneInfo | None = None,
) -> list[str]:
	"""
	Build ordered per-day keys for cache output.
	"""
	if window_days < 1:
		return []
	tz_value = reset_tz or resolve_day_reset_timezone()
	start_date = window_start.astimezone(tz_value).date()
	keys = []
	for offset in range(window_days):
		day_key = (start_date + timedelta(days=offset)).isoformat()
		keys.append(day_key)
	return keys


#============================================
def add_record_to_daily_bucket(
	daily_buckets: dict[str, list[dict]],
	record: dict,
	fallback_day: str,
	reset_tz: ZoneInfo | None = None,
) -> str:
	"""
	Add one record to its day-bucket list.
	"""
	day_key = timestamp_to_day_key(
		record.get("event_time", ""),
		fallback_day,
		reset_tz=reset_tz,
	)
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
	default_user = pipeline_settings.get_github_username(settings, "vosslab")
	user = args.user.strip() or default_user
	log_step(f"Using settings file: {settings_path}")
	log_step(f"Using GitHub user: {user}")
	window_days = resolve_window_days(args)
	day_reset_tz = resolve_day_reset_timezone()
	day_reset_tz_name = resolve_day_reset_timezone_name()
	window_start, window_end = compute_completed_window_utc(
		window_days,
		reset_tz=day_reset_tz,
	)
	window_start_local = window_start.astimezone(day_reset_tz)
	window_end_local = window_end.astimezone(day_reset_tz)
	log_step(
		f"Active window: {window_start.isoformat()} -> {window_end.isoformat()} "
		+ f"({window_days} day(s))"
	)
	log_step(
		"Reset window: "
		+ f"{window_start_local.isoformat()} -> {window_end_local.isoformat()} "
		+ f"(reset at {DAY_RESET_HOUR_LOCAL:02d}:00 {day_reset_tz_name})"
	)

	token = pipeline_settings.get_setting_str(settings, ["github", "token"], "")
	if token:
		log_step("Using authenticated GitHub API mode via settings.yaml github.token.")
	else:
		log_step("Using unauthenticated GitHub API mode (lower rate limit).")
	api_cache_dir = pipeline_settings.resolve_user_scoped_out_path(
		os.path.join("out", "cache", "github_api"),
		os.path.join("out", "cache", "github_api"),
		user,
	)

	try:
		client = github_client.GitHubClient(token, log_fn=log_step, cache_dir=api_cache_dir)
	except RuntimeError as error:
		log_step(str(error))
		log_step("Aborting fetch run before network calls.")
		return
	stopped_due_to_rate_limit = False
	stopped_reason = ""
	log_step("Fetching repository list.")
	repos: list[dict] = load_repo_list_cache(user, window_end)
	if repos:
		log_step(
			f"Repository list cache hit: {len(repos)} repo(s) from {repo_list_cache_path(user)}"
		)
	else:
		stale_repos = load_repo_list_cache(user, window_end, max_age_seconds=None)
		if stale_repos:
			repos = stale_repos
			log_step(
				"Repository list stale-cache fallback: "
				+ f"{len(repos)} repo(s) from {repo_list_cache_path(user)}"
			)
		else:
			try:
				repo_iter = client.list_repos(user)
				repo_objects = list(repo_iter)
				repos = [repo_to_dict(repo_obj) for repo_obj in repo_objects]
				cache_path = save_repo_list_cache(user, window_end, repos)
				log_step(f"Repository list cache refreshed: {len(repos)} repo(s) -> {cache_path}")
			except github_client.RateLimitError as error:
				stopped_due_to_rate_limit = True
				stopped_reason = str(error)
				log_step(stopped_reason)
				log_step("Repository listing stopped by rate limit; writing summary-only output.")
	if args.max_repos > 0:
		repos = repos[: args.max_repos]
		log_step(f"Applied --max-repos cap: {len(repos)} repo(s).")
	else:
		log_step(f"Repository candidates: {len(repos)}.")

	scoped_output_arg = pipeline_settings.resolve_user_scoped_out_path(
		args.output,
		"out/github_data.jsonl",
		user,
	)
	scoped_daily_cache_dir = pipeline_settings.resolve_user_scoped_out_path(
		args.daily_cache_dir,
		"out/daily_cache",
		user,
	)
	date_text = window_start_local.date().isoformat()
	dated_output = date_stamp_output_path(scoped_output_arg, date_text)
	output_path = os.path.abspath(dated_output)
	output_dir = os.path.dirname(output_path)
	os.makedirs(output_dir, exist_ok=True)
	log_step(f"Using local date stamp for fetch output filename: {date_text}")
	log_step(f"Writing JSONL output to: {output_path}")

	record_counts = {
		"repo": 0,
		"commit": 0,
		"issue": 0,
		"pull_request": 0,
		"repo_changelog": 0,
	}
	daily_buckets: dict[str, list[dict]] = {}
	day_keys = build_window_day_keys(window_start, window_days, reset_tz=day_reset_tz)
	fallback_day = day_keys[-1] if day_keys else date_text

	with open(output_path, "w", encoding="utf-8") as handle:
		start_record = {
			"record_type": "run_metadata",
			"user": user,
			"window_start": window_start.isoformat(),
			"window_end": window_end.isoformat(),
			"window_days": window_days,
			"fetched_at": window_end.isoformat(),
			"source": "fetch_github_data.py",
			"daily_cache_dir": os.path.abspath(scoped_daily_cache_dir),
		}
		write_jsonl_line(handle, start_record)

		for repo in repos:
			if repo.get("fork") and not args.include_forks:
				log_step(f"Skipped repo: {repo.get('full_name') or '(unknown)'}")
				continue
			repo_full_name = repo.get("full_name") or ""
			repo_name = repo.get("name") or ""
			if not repo_full_name:
				continue

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
				log_step(f"Skipped repo: {repo_full_name}")
				continue
			log_step(f"Processing repo: {repo_full_name}")
			repo_activity_count = 0
			repo_commit_count = 0

			try:
				commits = client.list_commits(repo_full_name, window_start, window_end)
			except github_client.RateLimitError as error:
				stopped_due_to_rate_limit = True
				stopped_reason = str(error)
				log_step(stopped_reason)
				log_step(f"Skipped repo: {repo_full_name}")
				continue
			for commit_obj in commits:
				commit = commit_to_dict(commit_obj)
				repo_commit_count += 1
				if repo_commit_count == 1:
					repo_record = build_repo_record(
						user,
						window_start,
						window_end,
						repo,
					)
					write_jsonl_line(handle, repo_record)
					add_record_to_daily_bucket(
						daily_buckets,
						repo_record,
						fallback_day,
						reset_tz=day_reset_tz,
					)
					record_counts["repo"] += 1
				commit_record = build_commit_record(
					user,
					window_start,
					window_end,
					repo_full_name,
					repo_name,
					commit,
				)
				write_jsonl_line(handle, commit_record)
				add_record_to_daily_bucket(
					daily_buckets,
					commit_record,
					fallback_day,
					reset_tz=day_reset_tz,
				)
				record_counts["commit"] += 1
				repo_activity_count += 1
			log_step(f"Repo {repo_full_name}: collected {repo_commit_count} commit record(s).")
			if repo_commit_count < 1:
				log_step(f"Skipped repo: {repo_full_name}")
				continue

			if (not args.skip_changelog) and (repo_recent or repo_activity_count > 0):
				ref_name = repo.get("default_branch") or ""
				try:
					changelog_info = fetch_repo_changelog_content(
						client,
						repo_full_name,
						ref_name,
					)
				except github_client.RateLimitError as error:
					stopped_due_to_rate_limit = True
					stopped_reason = str(error)
					log_step(stopped_reason)
					log_step(f"Skipped repo: {repo_full_name}")
					continue
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
					add_record_to_daily_bucket(
						daily_buckets,
						changelog_record,
						fallback_day,
						reset_tz=day_reset_tz,
					)
					record_counts["repo_changelog"] += 1

		end_record = {
			"record_type": "run_summary",
			"user": user,
			"window_start": window_start.isoformat(),
			"window_end": window_end.isoformat(),
			"window_days": window_days,
			"fetched_at": utc_now().isoformat(),
			"record_counts": record_counts,
			"daily_cache_dir": os.path.abspath(scoped_daily_cache_dir),
			"stopped_due_to_rate_limit": stopped_due_to_rate_limit,
			"stop_reason": stopped_reason,
		}
		write_jsonl_line(handle, end_record)

	written_daily_files = write_daily_cache_files(
		scoped_daily_cache_dir,
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
		+ f"{len(written_daily_files)} in {os.path.abspath(scoped_daily_cache_dir)}"
	)
	if stopped_due_to_rate_limit:
		log_step("Run finished with partial data due to GitHub API rate limiting.")
	usage = client.api_usage_snapshot()
	log_step(
		"GitHub API usage: "
		+ f"calls={usage.get('api_call_count', 0)}, "
		+ f"cache_hits={usage.get('cache_hit_count', 0)}, "
		+ f"cache_misses={usage.get('cache_miss_count', 0)}"
	)


if __name__ == "__main__":
	main()
