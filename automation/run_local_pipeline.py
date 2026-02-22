#!/usr/bin/env python3
import argparse
import os
import random
import subprocess
import time
from datetime import datetime

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
		"--num-speakers",
		type=int,
		default=3,
		help="Speaker count for podcast script stage (default: 3).",
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
def make_stage_commands(args: argparse.Namespace, date_text: str) -> list[tuple[str, list[str]]]:
	"""
	Build ordered stage command list.
	"""
	window_flag = resolve_window_flag(args)
	fetch_output = f"out/github_data_{date_text}.jsonl"
	stages = [
		(
			"fetch",
			[
				"python3",
				"pipeline/fetch_github_data.py",
				"--settings",
				args.settings,
				window_flag,
				"--output",
				fetch_output,
				"--daily-cache-dir",
				"out/daily_cache",
			],
		),
		(
			"outline",
			[
				"python3",
				"pipeline/outline_github_data.py",
				"--settings",
				args.settings,
				"--input",
				fetch_output,
				"--outline-json",
				"out/outline.json",
				"--outline-txt",
				"out/outline.txt",
			],
		),
		(
			"blog",
			[
				"python3",
				"pipeline/outline_to_blog_post.py",
				"--settings",
				args.settings,
				"--input",
				"out/outline.json",
				"--output",
				"out/blog_post.md",
				"--word-limit",
				"500",
			],
		),
		(
			"bluesky",
			[
				"python3",
				"pipeline/outline_to_bluesky_post.py",
				"--settings",
				args.settings,
				"--input",
				"out/outline.json",
				"--output",
				"out/bluesky_post.txt",
				"--char-limit",
				"140",
			],
		),
		(
			"podcast_script",
			[
				"python3",
				"pipeline/outline_to_podcast_script.py",
				"--settings",
				args.settings,
				"--input",
				"out/outline.json",
				"--output",
				"out/podcast_script.txt",
				"--num-speakers",
				str(args.num_speakers),
				"--word-limit",
				"500",
			],
		),
	]
	return stages


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
	date_text = datetime.now().astimezone().strftime("%Y-%m-%d")
	log_step(console, f"Using local date stamp for fetch output: {date_text}", style="cyan")

	stage_rows: list[tuple[str, str, str]] = []
	for stage_name, stage_command in make_stage_commands(args, date_text):
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
		except subprocess.CalledProcessError:
			elapsed = time.time() - stage_start
			stage_rows.append((stage_name, "[red]failed[/red]", f"{elapsed:.1f}"))
			render_summary_table(console, stage_rows)
			raise RuntimeError(f"Pipeline aborted at stage: {stage_name}")

	render_summary_table(console, stage_rows)
	log_step(console, f"Pipeline run complete: {os.path.join(repo_root, 'out')}", style="green")


if __name__ == "__main__":
	main()
