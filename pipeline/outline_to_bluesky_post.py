#!/usr/bin/env python3
import argparse
import json
import os

import pipeline_text_utils


#============================================
def parse_args() -> argparse.Namespace:
	"""
	Parse command-line arguments.
	"""
	parser = argparse.ArgumentParser(
		description="Render a <=140 character Bluesky post from outline JSON."
	)
	parser.add_argument(
		"--input",
		default="out/outline.json",
		help="Path to outline JSON input.",
	)
	parser.add_argument(
		"--output",
		default="out/bluesky_post.txt",
		help="Path to output text file.",
	)
	parser.add_argument(
		"--char-limit",
		type=int,
		default=140,
		help="Maximum character count for Bluesky text.",
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
def build_bluesky_text(outline: dict) -> str:
	"""
	Build one short social post from outline data.
	"""
	user = outline.get("user", "unknown")
	totals = outline.get("totals", {})
	repos = outline.get("repo_activity", [])
	repo_label = "n/a"
	if repos:
		repo_label = repos[0].get("repo_name") or repos[0].get("repo_full_name") or "n/a"

	text = (
		f"{user} weekly GitHub: {totals.get('commit_records', 0)} commits, "
		f"{totals.get('pull_request_records', 0)} PRs, "
		f"{totals.get('issue_records', 0)} issues. Top repo: {repo_label}."
	)
	return text


#============================================
def main() -> None:
	"""
	Generate Bluesky text with a hard character limit.
	"""
	args = parse_args()
	outline = load_outline(args.input)
	text = build_bluesky_text(outline)
	trimmed = pipeline_text_utils.trim_to_char_limit(text, args.char_limit)
	pipeline_text_utils.assert_char_limit(trimmed, args.char_limit)

	output_path = os.path.abspath(args.output)
	os.makedirs(os.path.dirname(output_path), exist_ok=True)
	with open(output_path, "w", encoding="utf-8") as handle:
		handle.write(trimmed)
		handle.write("\n")

	print(f"Wrote {output_path} ({len(trimmed)} chars)")


if __name__ == "__main__":
	main()
