#!/usr/bin/env python3
import argparse
import json
import math
import os
import re
import sys
from datetime import datetime

from podlib import pipeline_settings
from podlib import pipeline_text_utils


WORD_RE = re.compile(r"[A-Za-z0-9']+")
DATE_STAMP_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


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
		help="Path to output Markdown blog post (local date stamp added to filename).",
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
def describe_llm_execution_path(transport_name: str, model_override: str) -> str:
	"""
	Describe configured LLM transport execution order.
	"""
	model_label = model_override or "auto"
	if transport_name == "ollama":
		return f"ollama(model={model_label})"
	if transport_name == "apple":
		return "apple(local foundation models)"
	if transport_name == "auto":
		return f"apple(local foundation models) -> ollama(model={model_label})"
	return transport_name


#============================================
def create_llm_client(transport_name: str, model_override: str, quiet: bool) -> object:
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
	return llm.LLMClient(transports=transports, quiet=quiet)


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
	}
	return context


#============================================
def compute_repo_pass_word_target(repo_count: int, word_limit: int) -> int:
	"""
	Compute per-repo generation target using multi-pass heuristic.
	"""
	if repo_count <= 1:
		return word_limit
	raw_target = math.ceil((2 * word_limit) / (repo_count - 1))
	return max(100, raw_target)


#============================================
def build_blog_markdown_prompt(outline: dict, word_limit: int) -> str:
	"""
	Build fallback prompt for human-readable Markdown blog generation.
	"""
	context_json = json.dumps(build_blog_context(outline), ensure_ascii=True, indent=2)
	prompt = (
		"You are writing a daily engineering blog update from GitHub activity data.\n"
		"Write a human-readable Markdown post for MkDocs Material.\n"
		f"Target length: about {word_limit} words.\n"
		"Required format:\n"
		"- Markdown only (no HTML).\n"
		"- One H1 title chosen by you.\n"
		"- Keep structure simple and readable; avoid outline-style section dumping.\n"
		"- Use short paragraphs and occasional bullets only when they improve clarity.\n"
		"- Keep factual and avoid invented details.\n"
		"- Include repository names exactly as provided.\n"
		"- Include concrete numbers from the data (commits/issues/PRs).\n"
		"- Mention at least two repositories by name.\n"
		"Avoid these patterns:\n"
		"- Do not give writing advice or mention 'blueprint' or 'the outline above'.\n"
		"- Do not ask readers to comment or provide calls-to-action.\n"
		"- Do not use generic endings like 'We want to hear from you'.\n\n"
		"Context JSON:\n"
		f"{context_json}\n"
	)
	return prompt


#============================================
def build_repo_blog_markdown_prompt(
	outline: dict,
	repo_bucket: dict,
	repo_index: int,
	repo_total: int,
	word_target: int,
) -> str:
	"""
	Build one repo-focused draft prompt for multi-pass generation.
	"""
	repo_context = {
		"user": outline.get("user", "unknown"),
		"window_start": outline.get("window_start", ""),
		"window_end": outline.get("window_end", ""),
		"repo_index": repo_index,
		"repo_total": repo_total,
		"repo": {
			"repo_full_name": repo_bucket.get("repo_full_name", ""),
			"description": repo_bucket.get("description", ""),
			"language": repo_bucket.get("language", ""),
			"commit_count": repo_bucket.get("commit_count", 0),
			"issue_count": repo_bucket.get("issue_count", 0),
			"pull_request_count": repo_bucket.get("pull_request_count", 0),
			"latest_event_time": repo_bucket.get("latest_event_time", ""),
			"commit_messages": list(repo_bucket.get("commit_messages", []))[:10],
			"issue_titles": list(repo_bucket.get("issue_titles", []))[:10],
			"pull_request_titles": list(repo_bucket.get("pull_request_titles", []))[:10],
		},
		"overall_totals": outline.get("totals", {}),
		"top_notable_commit_messages": list(outline.get("notable_commit_messages", []))[:12],
	}
	context_json = json.dumps(repo_context, ensure_ascii=True, indent=2)
	return (
		"You are writing one candidate daily engineering blog draft.\n"
		f"This draft must focus on repository {repo_index} of {repo_total}.\n"
		f"Target length: about {word_target} words.\n"
		"Required format:\n"
		"- Markdown only (no HTML).\n"
		"- One H1 title chosen by you.\n"
		"- Human-readable narrative style, not a deterministic outline dump.\n"
		"- Include concrete repo metrics and specific commit/issue/PR details.\n"
		"- Mention the repo name exactly as provided.\n"
		"Avoid:\n"
		"- Writing advice, templates, or educational meta-content about blogging.\n"
		"- Reader call-to-action (comments, follow, subscribe, etc.).\n\n"
		"Context JSON:\n"
		f"{context_json}\n"
	)


#============================================
def build_final_blog_trim_prompt(
	outline: dict,
	best_draft: dict,
	word_limit: int,
) -> str:
	"""
	Build final trim prompt from the single best repo draft.
	"""
	context = {
		"user": outline.get("user", "unknown"),
		"window_start": outline.get("window_start", ""),
		"window_end": outline.get("window_end", ""),
		"totals": outline.get("totals", {}),
		"selected_repo_full_name": best_draft.get("repo_full_name", ""),
		"selected_repo_word_count": best_draft.get("word_count", 0),
		"selected_repo_markdown": best_draft.get("markdown", ""),
	}
	context_json = json.dumps(context, ensure_ascii=True, indent=2)
	return (
		"You are revising one daily engineering blog draft.\n"
		f"Target length: about {word_limit} words.\n"
		"Use the selected draft below as source material and pare it down to the target length.\n"
		"Keep the strongest details and preserve a natural human tone.\n"
		"Required format:\n"
		"- Markdown only (no HTML).\n"
		"- One H1 title chosen by you.\n"
		"- Natural, human-readable narrative with specific repo details and numbers.\n"
		"Avoid:\n"
		"- Writing-advice/meta content.\n"
		"- Reader call-to-action text.\n"
		"- Generic filler conclusions.\n\n"
		"Context JSON:\n"
		f"{context_json}\n"
	)


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
def normalize_markdown_blog(markdown_text: str) -> str:
	"""
	Salvage imperfect blog markdown into a usable shape.
	"""
	clean = (markdown_text or "").strip()
	if not clean:
		return ""
	lines = clean.splitlines()
	first_nonempty_index = -1
	for index, line in enumerate(lines):
		if line.strip():
			first_nonempty_index = index
			break
	if first_nonempty_index < 0:
		return ""
	first_line = lines[first_nonempty_index].lstrip()
	if first_line.startswith("# "):
		return clean
	if first_line.startswith("## "):
		lines[first_nonempty_index] = "# " + first_line[3:]
		return "\n".join(lines).strip()
	return "# Daily Engineering Update\n\n" + clean


#============================================
def blog_quality_issue(markdown_text: str) -> str:
	"""
	Return a validation issue string when blog markdown is unusable.
	"""
	clean = markdown_text.strip()
	if not clean:
		return "empty output"
	lower = clean.lower()
	if ("error_code" in lower) or ("generationerror" in lower):
		return "llm returned error payload"
	if clean.startswith("{") and clean.endswith("}"):
		return "llm returned structured error/object text"
	return ""


#============================================
def generate_blog_markdown_with_llm(
	outline: dict,
	transport_name: str,
	model_override: str,
	max_tokens: int,
	word_limit: int,
	logger=None,
) -> str:
	"""
	Generate Markdown blog body with multi-pass local-llm-wrapper flow.
	"""
	client = create_llm_client(transport_name, model_override, quiet=False)
	repo_buckets = list(outline.get("repo_activity", []))[:8]
	repo_total = len(repo_buckets)

	candidate_drafts: list[dict] = []
	if repo_total > 0:
		repo_word_target = compute_repo_pass_word_target(repo_total, word_limit)
		if logger:
			logger(
				"Running incremental repo drafts: "
				+ f"{repo_total} draft(s), per-repo target={repo_word_target} words."
			)
		for index, repo_bucket in enumerate(repo_buckets, start=1):
			repo_name = repo_bucket.get("repo_full_name", "")
			if logger:
				logger(
					f"Generating repo draft {index}/{repo_total} for {repo_name} "
					+ f"(target={repo_word_target} words)."
				)
			prompt = build_repo_blog_markdown_prompt(
				outline,
				repo_bucket,
				index,
				repo_total,
				repo_word_target,
			)
			repo_markdown = client.generate(
				prompt=prompt,
				purpose=f"repo draft {index} of {repo_total}",
				max_tokens=max_tokens,
			).strip()
			repo_markdown = normalize_markdown_blog(repo_markdown)
			repo_issue = blog_quality_issue(repo_markdown)
			if repo_issue:
				if logger:
					logger(
						f"Repo draft {index}/{repo_total} flagged ({repo_issue}); retrying once."
					)
				retry_prompt = (
					"Regenerate this repo draft as clean Markdown.\n"
					+ f"Target around {repo_word_target} words.\n"
					+ "No reader call-to-action. No meta blogging advice.\n\n"
					+ prompt
				)
				repo_markdown = client.generate(
					prompt=retry_prompt,
					purpose=f"repo draft regenerate {index} of {repo_total}",
					max_tokens=max_tokens,
				).strip()
				repo_markdown = normalize_markdown_blog(repo_markdown)
				repo_issue = blog_quality_issue(repo_markdown)
			if repo_issue:
				if logger:
					logger(
						f"Repo draft {index}/{repo_total} skipped after retry ({repo_issue})."
					)
				continue
			repo_words = pipeline_text_utils.count_words(repo_markdown)
			if logger:
				logger(
					f"Repo draft {index}/{repo_total} accepted ({repo_words} words)."
				)
			candidate_drafts.append(
				{
					"repo_full_name": repo_name,
					"markdown": repo_markdown,
					"word_count": repo_words,
					"score": 1000 - abs(repo_words - repo_word_target),
				}
			)

	if not candidate_drafts:
		if logger:
			logger("No valid repo drafts; running single-pass fallback blog generation.")
		fallback_prompt = build_blog_markdown_prompt(outline, word_limit)
		fallback = client.generate(
			prompt=fallback_prompt,
			purpose="daily markdown blog fallback",
			max_tokens=max_tokens,
		).strip()
		fallback = normalize_markdown_blog(fallback)
		fallback_issue = blog_quality_issue(fallback)
		if fallback_issue:
			if logger:
				logger(f"Fallback draft flagged ({fallback_issue}); retrying once.")
			fallback_retry_prompt = (
				"Regenerate the blog post as clean Markdown.\n"
				+ f"Target around {word_limit} words.\n\n"
				+ fallback_prompt
			)
			fallback_retry = client.generate(
				prompt=fallback_retry_prompt,
				purpose="daily markdown blog fallback regenerate",
				max_tokens=max_tokens,
			).strip()
			fallback_retry = normalize_markdown_blog(fallback_retry)
			if fallback_retry:
				if logger:
					retry_words = pipeline_text_utils.count_words(fallback_retry)
					logger(f"Fallback retry produced {retry_words} words.")
				return fallback_retry
		return fallback

	candidate_drafts.sort(key=lambda item: item.get("score", 0), reverse=True)
	best_candidate = candidate_drafts[0]
	if logger:
		logger(
			"Selected best repo draft for final trim: "
			+ f"{best_candidate.get('repo_full_name', '')} "
			+ f"({best_candidate.get('word_count', 0)} words)."
		)
	final_prompt = build_final_blog_trim_prompt(outline, best_candidate, word_limit)
	if logger:
		logger(f"Generating final trim pass (target={word_limit} words).")
	final_markdown = client.generate(
		prompt=final_prompt,
		purpose="daily markdown blog final trim",
		max_tokens=max_tokens,
	).strip()
	final_markdown = normalize_markdown_blog(final_markdown)
	final_issue = blog_quality_issue(final_markdown)
	if final_issue:
		if logger:
			logger(f"Final trim output flagged ({final_issue}); retrying once.")
		retry_prompt = (
			"Regenerate the final blog post as clean Markdown.\n"
			+ f"Target around {word_limit} words.\n"
			+ "No reader call-to-action. No blogging advice content.\n\n"
			+ final_prompt
		)
		final_markdown = client.generate(
			prompt=retry_prompt,
			purpose="daily markdown blog final regenerate",
			max_tokens=max_tokens,
		).strip()
		final_markdown = normalize_markdown_blog(final_markdown)
	if logger:
		final_words = pipeline_text_utils.count_words(final_markdown)
		logger(f"Final trim output ready ({final_words} words; target={word_limit}).")
	return final_markdown


#============================================
def local_date_stamp() -> str:
	"""
	Return local-date stamp for filenames.
	"""
	return datetime.now().astimezone().strftime("%Y-%m-%d")


#============================================
def date_stamp_output_path(output_path: str, date_text: str) -> str:
	"""
	Ensure output filename includes one local-date stamp and no time stamp.
	"""
	candidate = (output_path or "").strip() or "out/blog_post.md"
	candidate = candidate.replace("{date}", date_text)
	directory, filename = os.path.split(candidate)
	if not filename:
		filename = "blog_post.md"
	stem, extension = os.path.splitext(filename)
	if not extension:
		extension = ".md"
	if DATE_STAMP_RE.search(filename):
		dated_filename = filename
	else:
		dated_filename = f"{stem}_{date_text}{extension}"
	return os.path.join(directory, dated_filename)


#============================================
def main() -> None:
	"""
	Generate Markdown blog post with LLM using target word count.
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
	log_step(
		"LLM execution path for this run: "
		+ describe_llm_execution_path(transport_name, model_override)
	)
	log_step("Loading outline JSON.")
	outline = load_outline(args.input)
	log_step("Generating Markdown blog post with incremental drafts and final trim pass.")
	try:
		markdown = generate_blog_markdown_with_llm(
			outline,
			transport_name=transport_name,
			model_override=model_override,
			max_tokens=max_tokens,
			word_limit=args.word_limit,
			logger=log_step,
		)
	except RuntimeError as error:
		log_step(f"Blog generation failed: {error}")
		log_step("No blog file written.")
		return
	date_text = local_date_stamp()
	dated_output = date_stamp_output_path(args.output, date_text)
	output_path = os.path.abspath(dated_output)
	log_step(f"Using local date stamp for blog filename: {date_text}")
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
