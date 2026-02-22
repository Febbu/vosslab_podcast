#!/usr/bin/env python3
import argparse
import glob
import json
import os
import re
from datetime import datetime
from datetime import timezone

from podlib import pipeline_settings


DATE_STAMP_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
DAILY_JSON_RE = re.compile(r"^github_outline-(\d{4}-\d{2}-\d{2})\.json$")
DEFAULT_DAILY_OUTLINES_DIR = "out/daily_outlines"
DEFAULT_OUTPUT_JSON = "out/outline.json"
DEFAULT_OUTPUT_MD = "out/compilation_outline.md"


#============================================
def log_step(message: str) -> None:
	"""
	Print one timestamped progress line.
	"""
	now_text = datetime.now().strftime("%H:%M:%S")
	print(f"[outline_compilation {now_text}] {message}", flush=True)


#============================================
def parse_args() -> argparse.Namespace:
	"""
	Parse command-line arguments.
	"""
	parser = argparse.ArgumentParser(
		description="Compile daily GitHub outlines into one requested-period outline."
	)
	window_group = parser.add_mutually_exclusive_group()
	window_group.add_argument(
		"--last-day",
		action="store_true",
		help="Compile one daily outline (default).",
	)
	window_group.add_argument(
		"--last-week",
		action="store_true",
		help="Compile up to 7 daily outlines.",
	)
	window_group.add_argument(
		"--last-month",
		action="store_true",
		help="Compile up to 30 daily outlines.",
	)
	parser.add_argument(
		"--settings",
		default="settings.yaml",
		help="YAML settings path for defaults.",
	)
	parser.add_argument(
		"--daily-outlines-dir",
		default=DEFAULT_DAILY_OUTLINES_DIR,
		help="Directory containing github_outline-YYYY-MM-DD.json daily files.",
	)
	parser.add_argument(
		"--output-json",
		default=DEFAULT_OUTPUT_JSON,
		help="Path to compiled outline JSON for downstream scripts.",
	)
	parser.add_argument(
		"--output-md",
		default=DEFAULT_OUTPUT_MD,
		help="Path to compiled Markdown outline.",
	)
	return parser.parse_args()


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
def resolve_window_label(window_days: int) -> str:
	"""
	Resolve filename label token from day count.
	"""
	if window_days == 1:
		return "day"
	if window_days == 7:
		return "week"
	if window_days == 30:
		return "month"
	return f"{window_days}days"


#============================================
def local_date_stamp() -> str:
	"""
	Return local date stamp for output filenames.
	"""
	return datetime.now().astimezone().strftime("%Y-%m-%d")


#============================================
def date_stamp_output_md(output_path: str, window_label: str, date_text: str) -> str:
	"""
	Ensure compiled markdown filename includes window label and date.
	"""
	candidate = (output_path or "").strip() or DEFAULT_OUTPUT_MD
	candidate = candidate.replace("{date}", date_text)
	directory, filename = os.path.split(candidate)
	if not filename:
		filename = "compilation_outline.md"
	stem, extension = os.path.splitext(filename)
	if not extension:
		extension = ".md"
	if DATE_STAMP_RE.search(filename):
		dated_filename = filename
	else:
		dated_filename = f"{stem}-{window_label}-{date_text}{extension}"
	return os.path.join(directory, dated_filename)


#============================================
def discover_daily_outline_json_files(daily_dir: str) -> list[tuple[str, str]]:
	"""
	Discover dated daily JSON outline files sorted by date.
	"""
	pattern = os.path.join(daily_dir, "github_outline-*.json")
	items: list[tuple[str, str]] = []
	for path in glob.glob(pattern):
		filename = os.path.basename(path)
		match = DAILY_JSON_RE.match(filename)
		if not match:
			continue
		items.append((match.group(1), path))
	items.sort(key=lambda item: item[0])
	return items


#============================================
def load_outline_json(path: str) -> dict:
	"""
	Load one outline JSON file.
	"""
	with open(path, "r", encoding="utf-8") as handle:
		return json.load(handle)


#============================================
def has_content(outline: dict) -> bool:
	"""
	Return True when outline includes repo commit activity.
	"""
	totals = outline.get("totals", {}) if isinstance(outline, dict) else {}
	repo_count = int(totals.get("repos", 0))
	commit_count = int(totals.get("commit_records", 0))
	return (repo_count > 0) and (commit_count > 0)


#============================================
def merge_repo_activity(merged_repos: dict[str, dict], bucket: dict) -> None:
	"""
	Merge one repo bucket into the compilation map.
	"""
	repo_full_name = str(bucket.get("repo_full_name") or "").strip()
	if not repo_full_name:
		return
	if repo_full_name not in merged_repos:
		merged_repos[repo_full_name] = {
			"repo_full_name": repo_full_name,
			"repo_name": bucket.get("repo_name", ""),
			"html_url": bucket.get("html_url", ""),
			"description": bucket.get("description", ""),
			"language": bucket.get("language", ""),
			"commit_count": 0,
			"issue_count": 0,
			"pull_request_count": 0,
			"commit_messages": [],
			"issue_titles": [],
			"pull_request_titles": [],
			"latest_event_time": "",
			"total_activity": 0,
		}
	target = merged_repos[repo_full_name]
	target["commit_count"] += int(bucket.get("commit_count", 0))
	target["issue_count"] += int(bucket.get("issue_count", 0))
	target["pull_request_count"] += int(bucket.get("pull_request_count", 0))
	for key in ("commit_messages", "issue_titles", "pull_request_titles"):
		for text in list(bucket.get(key, [])):
			if text and (text not in target[key]):
				target[key].append(text)
	latest = str(bucket.get("latest_event_time", "")).strip()
	if latest and (latest > str(target.get("latest_event_time", ""))):
		target["latest_event_time"] = latest
	target["total_activity"] = (
		target["commit_count"] + target["issue_count"] + target["pull_request_count"]
	)


#============================================
def compile_outlines(outlines: list[dict]) -> dict:
	"""
	Compile selected daily outlines into one merged outline dict.
	"""
	merged_repos: dict[str, dict] = {}
	notable_messages: list[str] = []
	user = "unknown"
	window_start = ""
	window_end = ""
	totals = {
		"repo_records": 0,
		"commit_records": 0,
		"issue_records": 0,
		"pull_request_records": 0,
		"run_metadata_records": 0,
		"run_summary_records": 0,
	}

	for outline in outlines:
		user = outline.get("user", user) or user
		if (not window_start) or (outline.get("window_start", "") < window_start):
			window_start = outline.get("window_start", window_start)
		if outline.get("window_end", "") > window_end:
			window_end = outline.get("window_end", window_end)
		source_totals = outline.get("totals", {})
		for key in totals:
			totals[key] += int(source_totals.get(key, 0))
		for bucket in list(outline.get("repo_activity", [])):
			merge_repo_activity(merged_repos, bucket)
		for message in list(outline.get("notable_commit_messages", [])):
			if message and (message not in notable_messages):
				notable_messages.append(message)

	repo_list = list(merged_repos.values())
	repo_list.sort(
		key=lambda item: (item.get("total_activity", 0), item.get("commit_count", 0), item.get("repo_full_name", "")),
		reverse=True,
	)
	return {
		"generated_at": datetime.now(timezone.utc).isoformat(),
		"user": user,
		"window_start": window_start,
		"window_end": window_end,
		"totals": {
			"repos": len(repo_list),
			"repo_records": totals["repo_records"],
			"commit_records": totals["commit_records"],
			"issue_records": totals["issue_records"],
			"pull_request_records": totals["pull_request_records"],
			"run_metadata_records": totals["run_metadata_records"],
			"run_summary_records": totals["run_summary_records"],
		},
		"repo_activity": repo_list,
		"notable_commit_messages": notable_messages[:50],
	}


#============================================
def render_compilation_markdown(compiled: dict, selected_days: list[str], window_label: str) -> str:
	"""
	Render compiled outline as Markdown.
	"""
	lines = []
	lines.append(f"# GitHub Compilation Outline ({window_label})")
	lines.append("")
	lines.append(f"- User: {compiled.get('user', 'unknown')}")
	lines.append(f"- Included day count: {len(selected_days)}")
	lines.append(f"- Included days: {', '.join(selected_days)}")
	lines.append(f"- Window: {compiled.get('window_start', '')} -> {compiled.get('window_end', '')}")
	lines.append("")
	lines.append("## Totals")
	totals = compiled.get("totals", {})
	lines.append(f"- Repos with activity: {totals.get('repos', 0)}")
	lines.append(f"- Commit records: {totals.get('commit_records', 0)}")
	lines.append(f"- Issue records: {totals.get('issue_records', 0)}")
	lines.append(f"- Pull request records: {totals.get('pull_request_records', 0)}")
	lines.append("")
	lines.append("## Repository Activity")
	for index, bucket in enumerate(list(compiled.get("repo_activity", []))[:20], start=1):
		lines.append(f"### {index}. {bucket.get('repo_full_name', '')}")
		lines.append(f"- Total activity: {bucket.get('total_activity', 0)}")
		lines.append(f"- Commits: {bucket.get('commit_count', 0)}")
		lines.append(f"- Issues: {bucket.get('issue_count', 0)}")
		lines.append(f"- Pull requests: {bucket.get('pull_request_count', 0)}")
		lines.append("")
	lines.append("## Notable Commit Messages")
	for message in list(compiled.get("notable_commit_messages", []))[:30]:
		lines.append(f"- {message}")
	lines.append("")
	return "\n".join(lines).strip() + "\n"


#============================================
def main() -> None:
	"""
	Compile daily outline snapshots into one downstream outline.
	"""
	args = parse_args()
	settings, settings_path = pipeline_settings.load_settings(args.settings)
	user = pipeline_settings.get_github_username(settings, "vosslab")
	window_days = resolve_window_days(args)
	window_label = resolve_window_label(window_days)
	daily_dir = pipeline_settings.resolve_user_scoped_out_path(
		args.daily_outlines_dir,
		DEFAULT_DAILY_OUTLINES_DIR,
		user,
	)
	output_json = pipeline_settings.resolve_user_scoped_out_path(
		args.output_json,
		DEFAULT_OUTPUT_JSON,
		user,
	)
	output_md_arg = pipeline_settings.resolve_user_scoped_out_path(
		args.output_md,
		DEFAULT_OUTPUT_MD,
		user,
	)
	date_text = local_date_stamp()
	output_md = date_stamp_output_md(output_md_arg, window_label, date_text)

	log_step(f"Using settings file: {settings_path}")
	log_step(f"Using GitHub user: {user}")
	log_step(f"Compiling window: {window_label} ({window_days} day(s))")
	log_step(f"Scanning daily outlines in: {os.path.abspath(daily_dir)}")
	available = discover_daily_outline_json_files(daily_dir)
	if not available:
		raise RuntimeError(f"No daily outline JSON files found in {os.path.abspath(daily_dir)}")
	selected = available[-window_days:]
	log_step(f"Selected {len(selected)} day file(s) before content filtering.")

	filtered_outlines = []
	selected_days = []
	for day_text, path in selected:
		outline = load_outline_json(path)
		if not has_content(outline):
			log_step(f"Skipping empty daily outline: {os.path.abspath(path)}")
			continue
		filtered_outlines.append(outline)
		selected_days.append(day_text)
	if not filtered_outlines:
		raise RuntimeError("No non-empty daily outlines available for compilation.")

	compiled = compile_outlines(filtered_outlines)
	compiled_markdown = render_compilation_markdown(compiled, selected_days, window_label)

	output_json_abs = os.path.abspath(output_json)
	output_md_abs = os.path.abspath(output_md)
	os.makedirs(os.path.dirname(output_json_abs), exist_ok=True)
	os.makedirs(os.path.dirname(output_md_abs), exist_ok=True)
	with open(output_json_abs, "w", encoding="utf-8") as handle:
		json.dump(compiled, handle, indent=2)
		handle.write("\n")
	with open(output_md_abs, "w", encoding="utf-8") as handle:
		handle.write(compiled_markdown)

	log_step(f"Wrote compiled outline JSON: {output_json_abs}")
	log_step(f"Wrote compiled outline Markdown: {output_md_abs}")


if __name__ == "__main__":
	main()
