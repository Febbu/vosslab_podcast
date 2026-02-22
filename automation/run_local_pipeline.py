#!/usr/bin/env python3
import argparse
import glob
import json
import os
import random
import subprocess
import time
from datetime import datetime

import yaml

try:
	import rich.console
	import rich.table
except ModuleNotFoundError as error:
	raise RuntimeError(
		"Missing dependency: rich. Install with: source source_me.sh && pip install -r pip_requirements.txt"
	) from error


#============================================
def log_step(console: rich.console.Console, message: str, style: str = "cyan") -> None:
	"""
	Print one timestamped progress line with color.
	"""
	now_text = datetime.now().strftime("%H:%M:%S")
	console.print(f"[run_local_pipeline {now_text}] {message}", style=style)


#============================================
def parse_args() -> argparse.Namespace:
	"""
	Parse command-line arguments.
	"""
	parser = argparse.ArgumentParser(
		description="Run local content pipeline with stage logs and retry handling."
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
		"--settings",
		default="settings.yaml",
		help="YAML settings path for pipeline defaults.",
	)
	parser.add_argument(
		"--max-retries",
		type=int,
		default=1,
		help="Retry count per stage on failure (default: 1).",
	)
	parser.add_argument(
		"--retry-wait-seconds",
		type=int,
		default=10,
		help="Wait seconds before retrying a failed stage (default: 10).",
	)
	parser.add_argument(
		"--no-api-calls",
		action="store_true",
		help="Skip fetch stage and reuse latest cached fetch JSONL to avoid GitHub API calls.",
	)
	parser.add_argument(
		"--no-continue",
		action="store_true",
		help="Regenerate all LLM outputs from scratch instead of reusing cached outlines/drafts.",
	)
	return parser.parse_args()


#============================================
def resolve_repo_root() -> str:
	"""
	Resolve repository root with git.
	"""
	result = subprocess.run(
		["git", "rev-parse", "--show-toplevel"],
		check=True,
		capture_output=True,
		text=True,
	)
	repo_root = result.stdout.strip()
	return repo_root


#============================================
def resolve_window_flag(args: argparse.Namespace) -> str:
	"""
	Resolve fetch window flag from args.
	"""
	if args.last_month:
		return "--last-month"
	if args.last_week:
		return "--last-week"
	return "--last-day"


#============================================
def run_stage_once(repo_root: str, command_args: list[str]) -> None:
	"""
	Run one stage command using the caller's existing environment.
	"""
	subprocess.run(
		command_args,
		cwd=repo_root,
		check=True,
	)


#============================================
def run_stage_with_retry(
	console: rich.console.Console,
	repo_root: str,
	stage_name: str,
	command_args: list[str],
	max_retries: int,
	retry_wait_seconds: int,
) -> float:
	"""
	Run one stage with retry and small random jitter.
	"""
	start = time.time()
	attempt = 0
	while True:
		attempt += 1
		log_step(
			console,
			f"Starting stage: {stage_name} (attempt {attempt}/{max_retries + 1})",
			style="cyan",
		)
		try:
			run_stage_once(repo_root, command_args)
			elapsed = time.time() - start
			log_step(console, f"Completed stage: {stage_name} ({elapsed:.1f}s)", style="green")
			return elapsed
		except subprocess.CalledProcessError as error:
			elapsed = time.time() - start
			log_step(
				console,
				f"Stage failed: {stage_name} ({elapsed:.1f}s, exit={error.returncode})",
				style="red",
			)
			if attempt > max_retries:
				raise
			wait_seconds = retry_wait_seconds + random.random()
			log_step(
				console,
				f"Waiting {wait_seconds:.1f}s before retrying stage: {stage_name}",
				style="yellow",
			)
			time.sleep(wait_seconds)


#============================================
def make_stage_commands(args: argparse.Namespace) -> list[tuple[str, list[str]]]:
	"""
	Build ordered stage command list.
	"""
	window_flag = resolve_window_flag(args)
	stages = [
		(
			"fetch",
			[
				"python3",
				"pipeline/fetch_github_data.py",
				"--settings",
				args.settings,
				window_flag,
			],
		),
		(
			"outline",
			[
				"python3",
				"pipeline/github_data_to_outline.py",
				"--settings",
				args.settings,
			] + (["--no-continue"] if args.no_continue else []),
		),
		(
			"outline_compilation",
			[
				"python3",
				"pipeline/outline_compilation.py",
				"--settings",
				args.settings,
				window_flag,
			],
		),
		(
			"blog",
			[
				"python3",
				"pipeline/outline_to_blog_post.py",
				"--settings",
				args.settings,
				"--word-limit",
				"500",
			] + (["--no-continue"] if args.no_continue else []),
		),
		(
			"bluesky",
			[
				"python3",
				"pipeline/blog_to_bluesky_post.py",
				"--settings",
				args.settings,
			],
		),
		(
			"podcast_script",
			[
				"python3",
				"pipeline/blog_to_podcast_script.py",
				"--settings",
				args.settings,
			],
		),
		(
			"podcast_audio",
			[
				"python3",
				"pipeline/script_to_audio_say.py",
				"--settings",
				args.settings,
			],
		),
	]
	if args.no_api_calls:
		stages = [item for item in stages if item[0] != "fetch"]
	return stages


#============================================
def load_fetch_summary(fetch_output_path: str) -> dict:
	"""
	Load run_summary record from fetch JSONL output.
	"""
	if not os.path.isfile(fetch_output_path):
		return {}
	summary = {}
	with open(fetch_output_path, "r", encoding="utf-8") as handle:
		for raw_line in handle:
			line = raw_line.strip()
			if not line:
				continue
			try:
				record = json.loads(line)
			except json.JSONDecodeError:
				continue
			if record.get("record_type") == "run_summary":
				summary = record
	return summary


#============================================
def render_summary_table(
	console: rich.console.Console,
	stage_rows: list[tuple[str, str, str]],
) -> None:
	"""
	Render final stage summary table.
	"""
	table = rich.table.Table(title="Local Pipeline Summary")
	table.add_column("Stage", style="bold cyan")
	table.add_column("Status", style="bold")
	table.add_column("Elapsed (s)", justify="right")
	for stage_name, status_text, elapsed_text in stage_rows:
		table.add_row(stage_name, status_text, elapsed_text)
	console.print(table)


#============================================
def load_settings_username(repo_root: str, settings_path_text: str) -> str:
	"""
	Load github.username from settings with vosslab fallback.
	"""
	if os.path.isabs(settings_path_text):
		settings_path = settings_path_text
	else:
		settings_path = os.path.join(repo_root, settings_path_text)
	if not os.path.isfile(settings_path):
		return "vosslab"
	with open(settings_path, "r", encoding="utf-8") as handle:
		data = yaml.safe_load(handle.read())
	if not isinstance(data, dict):
		return "vosslab"
	github = data.get("github")
	if not isinstance(github, dict):
		return "vosslab"
	username = str(github.get("username", "")).strip()
	if username:
		return username
	return "vosslab"


#============================================
def resolve_latest_fetch_output_path(repo_root: str, user: str) -> str:
	"""
	Resolve latest user-scoped fetch JSONL output file.
	"""
	base_dir = os.path.join(repo_root, "out", user)
	pattern = os.path.join(base_dir, "github_data_*.jsonl")
	candidates = [path for path in glob.glob(pattern) if os.path.isfile(path)]
	if not candidates:
		return os.path.join(base_dir, "github_data.jsonl")
	candidates.sort(key=os.path.getmtime, reverse=True)
	return candidates[0]


#============================================
def find_latest_match(base_dir: str, pattern: str) -> str:
	"""
	Return latest matching file path or empty string.
	"""
	full_pattern = os.path.join(base_dir, pattern)
	candidates = [path for path in glob.glob(full_pattern) if os.path.isfile(path)]
	if not candidates:
		return ""
	candidates.sort(key=os.path.getmtime, reverse=True)
	return candidates[0]


#============================================
def render_artifact_list(
	console: rich.console.Console,
	repo_root: str,
	user: str,
	date_text: str,
) -> None:
	"""
	Print final artifact path list for quick review.
	"""
	user_out = os.path.join(repo_root, "out", user)
	blog_path = find_latest_match(user_out, "blog_post_*.md")
	bluesky_path = find_latest_match(user_out, "bluesky_post-*.txt")
	podcast_script_path = find_latest_match(user_out, "podcast_script-*.txt")
	podcast_narration_path = find_latest_match(user_out, "podcast_narration-*.txt")
	podcast_audio_path = find_latest_match(user_out, "podcast_audio-*.mp3")
	narrator_audio_path = find_latest_match(user_out, "narrator_audio-*.mp3")

	log_step(console, "Final artifacts:", style="bold cyan")
	for label, path in [
		("blog", blog_path),
		("bluesky", bluesky_path),
		("podcast_script", podcast_script_path),
		("podcast_narration", podcast_narration_path),
		("podcast_audio", podcast_audio_path),
		("narrator_audio", narrator_audio_path),
	]:
		if not path:
			console.print(f"- {label}: (missing)", style="yellow")
			continue
		relative = os.path.relpath(path, repo_root)
		console.print(f"- {relative}", style="green")


#============================================
def main() -> None:
	"""
	Run local pipeline stages with colorful output and retries.
	"""
	args = parse_args()
	console = rich.console.Console()
	repo_root = resolve_repo_root()
	if not os.environ.get("PYTHONPATH"):
		log_step(
			console,
			"Warning: PYTHONPATH is empty. Run with: source source_me.sh && python3 automation/run_local_pipeline.py",
			style="yellow",
		)
	log_step(console, f"Starting local pipeline run from {repo_root}", style="cyan")
	log_step(console, f"Using settings file: {os.path.join(repo_root, args.settings)}", style="cyan")
	log_step(console, f"Window mode: {resolve_window_flag(args)}", style="cyan")
	user = load_settings_username(repo_root, args.settings)
	log_step(console, f"Using GitHub user: {user}", style="cyan")
	if args.no_api_calls:
		log_step(console, "Mode: --no-api-calls enabled (fetch stage skipped).", style="yellow")
	date_text = datetime.now().astimezone().strftime("%Y-%m-%d")
	log_step(console, f"Using local date stamp for fetch output: {date_text}", style="cyan")
	fetch_output_path = resolve_latest_fetch_output_path(repo_root, user)
	if args.no_api_calls and (not os.path.isfile(fetch_output_path)):
		raise RuntimeError(
			"No cached fetch output found for --no-api-calls mode. "
			+ f"Expected under {os.path.join(repo_root, 'out', user)}."
		)

	stage_rows: list[tuple[str, str, str]] = []
	for stage_name, stage_command in make_stage_commands(args):
		stage_start = time.time()
		try:
			elapsed = run_stage_with_retry(
				console,
				repo_root,
				stage_name,
				stage_command,
				args.max_retries,
				args.retry_wait_seconds,
			)
			stage_rows.append((stage_name, "[green]ok[/green]", f"{elapsed:.1f}"))
			if stage_name == "fetch":
				fetch_output_path = resolve_latest_fetch_output_path(repo_root, user)
				summary = load_fetch_summary(fetch_output_path)
				record_counts = summary.get("record_counts", {}) if isinstance(summary, dict) else {}
				commit_records = int(record_counts.get("commit", 0))
				repo_records = int(record_counts.get("repo", 0))
				if commit_records < 1 or repo_records < 1:
					log_step(
						console,
						"No repos with commits found in active window; stopping pipeline after fetch.",
						style="yellow",
					)
					render_summary_table(console, stage_rows)
					return
		except subprocess.CalledProcessError:
			elapsed = time.time() - stage_start
			stage_rows.append((stage_name, "[red]failed[/red]", f"{elapsed:.1f}"))
			render_summary_table(console, stage_rows)
			raise RuntimeError(f"Pipeline aborted at stage: {stage_name}")

	render_summary_table(console, stage_rows)
	log_step(console, f"Pipeline run complete: {os.path.join(repo_root, 'out', user)}", style="green")
	render_artifact_list(console, repo_root, user, date_text)


if __name__ == "__main__":
	main()
