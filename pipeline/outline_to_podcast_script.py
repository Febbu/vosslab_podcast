#!/usr/bin/env python3
import argparse
import json
import os
from datetime import datetime

import pipeline_text_utils


#============================================
def log_step(message: str) -> None:
	"""
	Print one timestamped progress line.
	"""
	now_text = datetime.now().strftime("%H:%M:%S")
	print(f"[outline_to_podcast_script {now_text}] {message}", flush=True)


#============================================
def parse_args() -> argparse.Namespace:
	"""
	Parse command-line arguments.
	"""
	parser = argparse.ArgumentParser(
		description="Render a <=500 word N-speaker podcast script from outline JSON."
	)
	parser.add_argument(
		"--input",
		default="out/outline.json",
		help="Path to outline JSON input.",
	)
	parser.add_argument(
		"--output",
		default="out/podcast_script.txt",
		help="Path to output podcast script text file.",
	)
	parser.add_argument(
		"--num-speakers",
		type=int,
		default=3,
		help="Number of speakers to include in the script.",
	)
	parser.add_argument(
		"--word-limit",
		type=int,
		default=500,
		help="Maximum total words for spoken text.",
	)
	args = parser.parse_args()
	return args


#============================================
def load_outline(path: str) -> dict:
	"""
	Load outline JSON from disk.
	"""
	if not os.path.isfile(path):
		raise FileNotFoundError(f"Missing outline input: {path}")
	with open(path, "r", encoding="utf-8") as handle:
		outline = json.load(handle)
	return outline


#============================================
def build_speaker_labels(num_speakers: int) -> list[str]:
	"""
	Build normalized speaker labels.
	"""
	if num_speakers < 1:
		raise RuntimeError("num-speakers must be at least 1.")
	labels = []
	for index in range(1, num_speakers + 1):
		labels.append(f"SPEAKER_{index}")
	return labels


#============================================
def build_podcast_lines(outline: dict, speaker_labels: list[str]) -> list[tuple[str, str]]:
	"""
	Build ordered speaker lines before word-limit trimming.
	"""
	user = outline.get("user", "unknown")
	window_start = outline.get("window_start", "")
	window_end = outline.get("window_end", "")
	totals = outline.get("totals", {})
	repos = outline.get("repo_activity", [])
	notable = outline.get("notable_commit_messages", [])

	lines: list[tuple[str, str]] = []
	lines.append(
		(
			speaker_labels[0],
			f"Welcome to the weekly {user} GitHub report for {window_start} to {window_end}.",
		)
	)

	for index, label in enumerate(speaker_labels[1:], start=2):
		lines.append(
			(
				label,
				f"I am speaker {index}, and I will cover part of this week's engineering activity.",
			)
		)

	lines.append(
		(
			speaker_labels[0],
			f"We tracked {totals.get('commit_records', 0)} commits, "
			f"{totals.get('pull_request_records', 0)} pull requests, and "
			f"{totals.get('issue_records', 0)} issues.",
		)
	)

	for index, repo in enumerate(repos[:8]):
		label = speaker_labels[index % len(speaker_labels)]
		repo_name = repo.get("repo_full_name", "")
		commit_count = repo.get("commit_count", 0)
		pr_count = repo.get("pull_request_count", 0)
		issue_count = repo.get("issue_count", 0)
		description = (repo.get("description") or "").strip()
		line = (
			f"{repo_name} had {commit_count} commits, {pr_count} pull requests, "
			f"and {issue_count} issues."
		)
		if description:
			line += f" Summary: {description}."
		lines.append((label, line))

	for index, message in enumerate(notable[:8]):
		label = speaker_labels[index % len(speaker_labels)]
		lines.append((label, f"Notable commit subject: {message}."))

	lines.append(
		(
			speaker_labels[0],
			"That closes the weekly summary. We will return with the next GitHub activity report.",
		)
	)
	return lines


#============================================
def count_script_words(lines: list[tuple[str, str]]) -> int:
	"""
	Count total words in spoken text, excluding speaker labels.
	"""
	total = 0
	for _speaker, text in lines:
		total += pipeline_text_utils.count_words(text)
	return total


#============================================
def trim_lines_to_word_limit(
	lines: list[tuple[str, str]],
	word_limit: int,
) -> list[tuple[str, str]]:
	"""
	Trim script lines to satisfy a total word limit.
	"""
	if word_limit <= 0:
		return []
	remaining = word_limit
	trimmed: list[tuple[str, str]] = []
	for speaker, text in lines:
		words = pipeline_text_utils.extract_words(text)
		if not words:
			continue
		word_count = len(words)
		if remaining <= 0:
			break
		if word_count <= remaining:
			trimmed.append((speaker, text))
			remaining -= word_count
			continue
		shortened = " ".join(words[:remaining]).strip()
		if not shortened.endswith("..."):
			shortened += " ..."
		trimmed.append((speaker, shortened))
		remaining = 0
		break
	return trimmed


#============================================
def render_script_text(lines: list[tuple[str, str]]) -> str:
	"""
	Render speaker lines to ROLE: text format.
	"""
	rendered_lines = []
	for speaker, text in lines:
		rendered_lines.append(f"{speaker}: {text.strip()}")
	rendered = "\n".join(rendered_lines).strip() + "\n"
	return rendered


#============================================
def main() -> None:
	"""
	Generate N-speaker podcast script with a hard word limit.
	"""
	args = parse_args()
	log_step(
		"Starting podcast script stage with "
		+ f"input={os.path.abspath(args.input)}, output={os.path.abspath(args.output)}, "
		+ f"num_speakers={args.num_speakers}, word_limit={args.word_limit}"
	)
	log_step("Loading outline JSON.")
	outline = load_outline(args.input)
	log_step("Building speaker label set.")
	speaker_labels = build_speaker_labels(args.num_speakers)
	log_step("Constructing raw speaker lines from outline.")
	raw_lines = build_podcast_lines(outline, speaker_labels)
	log_step(f"Raw lines generated: {len(raw_lines)}")
	log_step("Applying global word limit trim to script lines.")
	trimmed_lines = trim_lines_to_word_limit(raw_lines, args.word_limit)
	log_step(f"Trimmed lines retained: {len(trimmed_lines)}")

	spoken_word_count = count_script_words(trimmed_lines)
	if spoken_word_count > args.word_limit:
		raise RuntimeError("Failed to enforce podcast script word limit.")

	used_speakers = {speaker for speaker, _text in trimmed_lines}
	missing_speakers = [label for label in speaker_labels if label not in used_speakers]
	if missing_speakers:
		raise RuntimeError(
			"Generated script is missing required speakers: "
			+ ", ".join(missing_speakers)
		)

	output_path = os.path.abspath(args.output)
	os.makedirs(os.path.dirname(output_path), exist_ok=True)
	script_text = render_script_text(trimmed_lines)
	log_step(f"Writing podcast script output to {output_path}")
	with open(output_path, "w", encoding="utf-8") as handle:
		handle.write(script_text)

	log_step(
		f"Wrote {output_path} "
		f"({spoken_word_count} words, {args.num_speakers} speakers)"
	)


if __name__ == "__main__":
	main()
