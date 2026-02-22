#!/usr/bin/env python3
import argparse
import html
import json
import os

import pipeline_text_utils


#============================================
def parse_args() -> argparse.Namespace:
	"""
	Parse command-line arguments.
	"""
	parser = argparse.ArgumentParser(
		description="Render a <=500 word webpage blog post from outline JSON."
	)
	parser.add_argument(
		"--input",
		default="out/outline.json",
		help="Path to outline JSON input.",
	)
	parser.add_argument(
		"--output",
		default="out/blog_post.html",
		help="Path to output HTML blog post.",
	)
	parser.add_argument(
		"--word-limit",
		type=int,
		default=500,
		help="Maximum word count for blog post body.",
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
def build_blog_paragraphs(outline: dict) -> list[str]:
	"""
	Build blog post paragraphs from outline data.
	"""
	user = outline.get("user", "unknown")
	window_start = outline.get("window_start", "")
	window_end = outline.get("window_end", "")
	totals = outline.get("totals", {})
	repos = outline.get("repo_activity", [])
	notable = outline.get("notable_commit_messages", [])

	paragraphs = []
	paragraphs.append(
		f"This weekly engineering update covers GitHub activity for {user} "
		f"from {window_start} to {window_end}."
	)
	paragraphs.append(
		f"Across the week, {totals.get('repos', 0)} repositories were active with "
		f"{totals.get('commit_records', 0)} commits, "
		f"{totals.get('pull_request_records', 0)} pull requests, and "
		f"{totals.get('issue_records', 0)} issues."
	)

	top_repos = repos[:5]
	for bucket in top_repos:
		repo_name = bucket.get("repo_full_name", "")
		commit_count = bucket.get("commit_count", 0)
		issue_count = bucket.get("issue_count", 0)
		pr_count = bucket.get("pull_request_count", 0)
		description = (bucket.get("description") or "").strip()
		line = (
			f"{repo_name} recorded {commit_count} commits, {pr_count} pull requests, "
			f"and {issue_count} issues."
		)
		if description:
			line += f" Description: {description}."
		paragraphs.append(line)

	if notable:
		highlight_count = min(6, len(notable))
		highlights = "; ".join(notable[:highlight_count])
		paragraphs.append("Notable commit subjects included: " + highlights + ".")

	paragraphs.append(
		"This post is generated from structured weekly data so the same pipeline can "
		"feed blog, social, and podcast channels with consistent facts."
	)
	return paragraphs


#============================================
def build_html_document(title: str, paragraphs: list[str]) -> str:
	"""
	Render a simple webpage-ready HTML document.
	"""
	parts = []
	parts.append("<!doctype html>")
	parts.append("<html lang='en'>")
	parts.append("<head>")
	parts.append("<meta charset='utf-8'>")
	parts.append("<meta name='viewport' content='width=device-width, initial-scale=1'>")
	parts.append(f"<title>{html.escape(title)}</title>")
	parts.append(
		"<style>body{font-family:Georgia,serif;max-width:760px;margin:2rem auto;"
		"line-height:1.6;padding:0 1rem;}h1{line-height:1.2;}</style>"
	)
	parts.append("</head>")
	parts.append("<body>")
	parts.append(f"<h1>{html.escape(title)}</h1>")
	for paragraph in paragraphs:
		parts.append(f"<p>{html.escape(paragraph)}</p>")
	parts.append("</body>")
	parts.append("</html>")
	document = "\n".join(parts) + "\n"
	return document


#============================================
def main() -> None:
	"""
	Generate the blog post with a hard word limit.
	"""
	args = parse_args()
	outline = load_outline(args.input)
	paragraphs = build_blog_paragraphs(outline)
	body_text = " ".join(paragraphs).strip()
	trimmed_body = pipeline_text_utils.trim_to_word_limit(body_text, args.word_limit)
	pipeline_text_utils.assert_word_limit(trimmed_body, args.word_limit)

	title = (
		f"{outline.get('user', 'unknown')} GitHub Weekly Update "
		f"{outline.get('window_start', '')} to {outline.get('window_end', '')}"
	)
	final_paragraphs = [segment.strip() for segment in trimmed_body.split(". ") if segment.strip()]
	final_paragraphs = [segment if segment.endswith(".") else segment + "." for segment in final_paragraphs]
	document = build_html_document(title, final_paragraphs)

	output_path = os.path.abspath(args.output)
	os.makedirs(os.path.dirname(output_path), exist_ok=True)
	with open(output_path, "w", encoding="utf-8") as handle:
		handle.write(document)

	word_count = pipeline_text_utils.count_words(trimmed_body)
	print(f"Wrote {output_path} ({word_count} words)")


if __name__ == "__main__":
	main()
