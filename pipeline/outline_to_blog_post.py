#!/usr/bin/env python3
import argparse
import json
import os
import re
import sys
from datetime import datetime

from podlib import pipeline_settings
from podlib import pipeline_text_utils


WORD_RE = re.compile(r"[A-Za-z0-9']+")


#============================================
def log_step(message: str) -> None:
	"""
	Print one timestamped progress line.
	"""
	now_text = datetime.now().strftime("%H:%M:%S")
	print(f"[outline_to_blog_post {now_text}] {message}", flush=True)


#============================================
def parse_args() -> argparse.Namespace:
	"""
	Parse command-line arguments.
	"""
	parser = argparse.ArgumentParser(
		description="Render a target-length Markdown blog post from outline JSON."
	)
	parser.add_argument(
		"--input",
		default="out/outline.json",
		help="Path to outline JSON input.",
	)
	parser.add_argument(
		"--output",
		default="out/blog_post.md",
		help="Path to output Markdown blog post.",
	)
	parser.add_argument(
		"--word-limit",
		type=int,
		default=500,
		help="Target word count for blog post body.",
	)
	parser.add_argument(
		"--settings",
		default="settings.yaml",
		help="YAML settings path for LLM defaults.",
	)
	parser.add_argument(
		"--llm-transport",
		choices=["ollama", "apple", "auto"],
		default=None,
		help="local-llm-wrapper transport selection (defaults from settings.yaml).",
	)
	parser.add_argument(
		"--llm-model",
		default=None,
		help="Optional model override (defaults from settings.yaml).",
	)
	parser.add_argument(
		"--llm-max-tokens",
		type=int,
		default=None,
		help="Maximum generation tokens (defaults from settings.yaml).",
	)
	args = parser.parse_args()
	return args


#============================================
def add_local_llm_wrapper_to_path() -> None:
	"""
	Add local-llm-wrapper path to sys.path when present.
	"""
	script_dir = os.path.dirname(os.path.abspath(__file__))
	repo_root = os.path.dirname(script_dir)
	candidates = [
		os.path.join(repo_root, "local-llm-wrapper"),
		os.path.join(repo_root, "pipeline", "local-llm-wrapper"),
	]
	for wrapper_repo in candidates:
		if not os.path.isdir(wrapper_repo):
			continue
		if wrapper_repo not in sys.path:
			sys.path.insert(0, wrapper_repo)
		return


#============================================
def create_llm_client(transport_name: str, model_override: str) -> object:
	"""
	Create local-llm-wrapper client for blog generation.
	"""
	add_local_llm_wrapper_to_path()
	import local_llm_wrapper.llm as llm

	model_choice = llm.choose_model(model_override or None)
	transports = []
	if transport_name == "ollama":
		transports.append(llm.OllamaTransport(model=model_choice))
	elif transport_name == "apple":
		transports.append(llm.AppleTransport())
	elif transport_name == "auto":
		transports.append(llm.AppleTransport())
		transports.append(llm.OllamaTransport(model=model_choice))
	else:
		raise RuntimeError(f"Unsupported llm transport: {transport_name}")
	return llm.LLMClient(transports=transports, quiet=True)


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
def build_blog_context(outline: dict) -> dict:
	"""
	Build compact blog generation context from outline data.
	"""
	repos = []
	for bucket in list(outline.get("repo_activity", []))[:8]:
		repos.append(
			{
				"repo_full_name": bucket.get("repo_full_name", ""),
				"description": bucket.get("description", ""),
				"language": bucket.get("language", ""),
				"commit_count": bucket.get("commit_count", 0),
				"issue_count": bucket.get("issue_count", 0),
				"pull_request_count": bucket.get("pull_request_count", 0),
				"latest_event_time": bucket.get("latest_event_time", ""),
				"commit_messages": list(bucket.get("commit_messages", []))[:8],
				"issue_titles": list(bucket.get("issue_titles", []))[:8],
				"pull_request_titles": list(bucket.get("pull_request_titles", []))[:8],
			}
		)
	context = {
		"user": outline.get("user", "unknown"),
		"window_start": outline.get("window_start", ""),
		"window_end": outline.get("window_end", ""),
		"totals": outline.get("totals", {}),
		"repos": repos,
		"notable_commit_messages": list(outline.get("notable_commit_messages", []))[:20],
		"llm_global_outline": (outline.get("llm_global_outline") or "")[:3000],
	}
	return context


#============================================
def build_blog_markdown_prompt(outline: dict, word_limit: int) -> str:
	"""
	Build prompt for human-readable Markdown blog generation.
	"""
	context_json = json.dumps(build_blog_context(outline), ensure_ascii=True, indent=2)
	prompt = (
		"You are writing a weekly engineering blog update from GitHub activity data.\n"
		"Write a human-readable Markdown post for MkDocs Material.\n"
		f"Target length: about {word_limit} words.\n"
		"Required format:\n"
		"- Markdown only (no HTML).\n"
		"- One H1 title.\n"
		"- 3 to 6 short sections with H2 headings.\n"
		"- Use bullet points only where helpful.\n"
		"- Keep factual and avoid invented details.\n"
		"- Include repository names exactly as provided.\n\n"
		"Context JSON:\n"
		f"{context_json}\n"
	)
	return prompt


#============================================
def trim_markdown_to_word_limit(markdown_text: str, word_limit: int) -> str:
	"""
	Trim markdown text to word limit while preserving early formatting.
	"""
	if word_limit <= 0:
		return ""
	matches = list(WORD_RE.finditer(markdown_text))
	if len(matches) <= word_limit:
		return markdown_text.strip()
	cutoff = matches[word_limit - 1].end()
	trimmed = markdown_text[:cutoff].rstrip()
	if not trimmed.endswith("..."):
		trimmed += "\n\n..."
	return trimmed


#============================================
def generate_blog_markdown_with_llm(
	outline: dict,
	transport_name: str,
	model_override: str,
	max_tokens: int,
	word_limit: int,
) -> str:
	"""
	Generate Markdown blog body with local-llm-wrapper.
	"""
	client = create_llm_client(transport_name, model_override)
	prompt = build_blog_markdown_prompt(outline, word_limit)
	markdown = client.generate(
		prompt=prompt,
		purpose="weekly markdown blog post",
		max_tokens=max_tokens,
	).strip()
	if pipeline_text_utils.count_words(markdown) <= word_limit:
		return markdown

	retry_prompt = (
		f"Rewrite the following Markdown to <= {word_limit} words while keeping headings "
		"and core facts. Markdown only.\n\n"
		+ markdown
	)
	shorter = client.generate(
		prompt=retry_prompt,
		purpose="shorten markdown blog post",
		max_tokens=max_tokens,
	).strip()
	return shorter


#============================================
def main() -> None:
	"""
	Generate Markdown blog post with LLM and hard word limit.
	"""
	args = parse_args()
	settings, settings_path = pipeline_settings.load_settings(args.settings)
	default_transport = pipeline_settings.get_enabled_llm_transport(settings)
	default_model = pipeline_settings.get_llm_provider_model(settings, default_transport)
	default_max_tokens = pipeline_settings.get_setting_int(settings, ["llm", "max_tokens"], 1200)
	transport_name = args.llm_transport or default_transport
	if transport_name not in {"ollama", "apple", "auto"}:
		raise RuntimeError(f"Unsupported llm transport in settings: {transport_name}")
	model_override = default_model
	if args.llm_model is not None:
		model_override = args.llm_model.strip()
	max_tokens = default_max_tokens if args.llm_max_tokens is None else args.llm_max_tokens
	if max_tokens < 1:
		raise RuntimeError("llm max tokens must be >= 1")
	if args.word_limit < 1:
		raise RuntimeError("word-limit must be >= 1")

	log_step(
		"Starting blog stage with "
		+ f"input={os.path.abspath(args.input)}, output={os.path.abspath(args.output)}, "
		+ f"word_limit={args.word_limit}"
	)
	log_step(f"Using settings file: {settings_path}")
	log_step(
		"Using LLM settings: "
		+ f"transport={transport_name}, model={model_override or 'auto'}, max_tokens={max_tokens}"
	)
	log_step("Loading outline JSON.")
	outline = load_outline(args.input)
	log_step("Generating Markdown blog post with LLM.")
	markdown = generate_blog_markdown_with_llm(
		outline,
		transport_name=transport_name,
		model_override=model_override,
		max_tokens=max_tokens,
		word_limit=args.word_limit,
	)
	output_path = os.path.abspath(args.output)
	output_dir = os.path.dirname(output_path)
	if output_dir:
		os.makedirs(output_dir, exist_ok=True)
	log_step(f"Writing blog output to {output_path}")
	with open(output_path, "w", encoding="utf-8") as handle:
		handle.write(markdown.strip() + "\n")

	word_count = pipeline_text_utils.count_words(markdown)
	log_step(f"Wrote {output_path} ({word_count} words; target={args.word_limit})")
	if word_count > args.word_limit:
		log_step(
			"Word target exceeded; keeping output as-is because this stage treats limit as target."
		)


if __name__ == "__main__":
	main()
