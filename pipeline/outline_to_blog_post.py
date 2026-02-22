#!/usr/bin/env python3
import argparse
import json
import os
import re
from datetime import datetime

from podlib import outline_draft_cache
from podlib import outline_llm
from podlib import pipeline_settings
from podlib import pipeline_text_utils


WORD_RE = re.compile(r"[A-Za-z0-9']+")
DATE_STAMP_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
DEFAULT_INPUT_PATH = "out/outline.json"
DEFAULT_OUTPUT_PATH = "out/blog_post.md"
DEFAULT_REPO_DRAFT_CACHE_DIR = "out/blog_repo_drafts"


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
		default=DEFAULT_INPUT_PATH,
		help="Path to outline JSON input.",
	)
	parser.add_argument(
		"--output",
		default=DEFAULT_OUTPUT_PATH,
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
	parser.add_argument(
		"--repo-draft-cache-dir",
		default=DEFAULT_REPO_DRAFT_CACHE_DIR,
		help="Directory for per-repo intermediate blog draft cache files.",
	)
	parser.add_argument(
		"--continue",
		dest="continue_mode",
		action="store_true",
		help="Reuse cached per-repo blog drafts when available (default: enabled).",
	)
	parser.add_argument(
		"--no-continue",
		dest="continue_mode",
		action="store_false",
		help="Disable per-repo blog draft cache reuse.",
	)
	parser.set_defaults(continue_mode=True)
	args = parser.parse_args()
	return args


#============================================
def describe_llm_execution_path(transport_name: str, model_override: str) -> str:
	"""
	Describe configured LLM transport execution order.
	"""
	return outline_llm.describe_llm_execution_path(transport_name, model_override)


#============================================
def create_llm_client(transport_name: str, model_override: str, quiet: bool) -> object:
	"""
	Create local-llm-wrapper client for blog generation.
	"""
	return outline_llm.create_llm_client(
		__file__,
		transport_name,
		model_override,
		quiet,
	)


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
def outline_has_activity(outline: dict) -> bool:
	"""
	Return True when outline has repo + commit activity to summarize.
	"""
	totals = outline.get("totals", {}) if isinstance(outline, dict) else {}
	repo_count = int(totals.get("repos", 0))
	commit_count = int(totals.get("commit_records", 0))
	return (repo_count > 0) and (commit_count > 0)


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
	return outline_llm.compute_incremental_target(repo_count, word_limit, 100)


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
		"- Write in human-readable paragraph form.\n"
		"- Keep structure simple and readable; avoid outline-style section dumping.\n"
		"- Use short paragraphs; avoid bullet-list-heavy output.\n"
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
		"- Write in human-readable paragraph form.\n"
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
	Build final assembly prompt from the single best repo draft.
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
		"Use the selected draft below as source material and produce a final post near the target length.\n"
		"Keep the strongest details and preserve a natural human tone.\n"
		"Required format:\n"
		"- Markdown only (no HTML).\n"
		"- One H1 title chosen by you.\n"
		"- Write in human-readable paragraph form.\n"
		"- Natural, human-readable narrative with specific repo details and numbers.\n"
		"Avoid:\n"
		"- Writing-advice/meta content.\n"
		"- Reader call-to-action text.\n"
		"- Generic filler conclusions.\n\n"
		"Context JSON:\n"
		f"{context_json}\n"
	)


#============================================
def build_final_blog_expand_prompt(
	outline: dict,
	candidate_drafts: list[dict],
	word_limit: int,
) -> str:
	"""
	Build final assembly prompt from top repo drafts.
	"""
	draft_blocks = []
	for index, item in enumerate(candidate_drafts, start=1):
		draft_blocks.append(
			{
				"candidate_index": index,
				"repo_full_name": item.get("repo_full_name", ""),
				"word_count": item.get("word_count", 0),
				"markdown": item.get("markdown", ""),
			}
		)
	context = {
		"user": outline.get("user", "unknown"),
		"window_start": outline.get("window_start", ""),
		"window_end": outline.get("window_end", ""),
		"totals": outline.get("totals", {}),
		"candidate_drafts": draft_blocks,
	}
	context_json = json.dumps(context, ensure_ascii=True, indent=2)
	min_words = max(1, word_limit // 2)
	return (
		"You are assembling the final daily engineering blog post.\n"
		+ f"Target length: about {word_limit} words.\n"
		+ f"Required hard range: between {min_words} and {word_limit * 2} words.\n"
		+ "Use multiple repo drafts as source material and produce one coherent final post near the target length.\n"
		+ "Required format:\n"
		+ "- Markdown only (no HTML).\n"
		+ "- One H1 title chosen by you.\n"
		+ "- Write in human-readable paragraph form.\n"
		+ "- Keep concrete repo names, metrics, and specific activity details.\n"
		+ "Avoid:\n"
		+ "- Writing-advice/meta content.\n"
		+ "- Reader call-to-action text.\n"
		+ "- Generic filler conclusions.\n\n"
		+ "Context JSON:\n"
		+ f"{context_json}\n"
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
def blog_word_band_issue(markdown_text: str, target_words: int) -> str:
	"""
	Return issue string when output falls outside hard acceptance band.
	"""
	if target_words < 1:
		return "invalid target"
	word_count = pipeline_text_utils.count_words(markdown_text)
	min_words = max(1, target_words // 2)
	max_words = target_words * 2
	if word_count < min_words:
		return f"word count below lower bound ({word_count} < {min_words})"
	if word_count > max_words:
		return f"word count above upper bound ({word_count} > {max_words})"
	return ""


#============================================
def enforce_blog_word_band(
	client,
	markdown_text: str,
	source_prompt: str,
	word_limit: int,
	max_tokens: int,
	logger=None,
	purpose: str = "blog word-band repair",
) -> str:
	"""
	Enforce hard blog word-band with one corrective regeneration pass.
	"""
	issue = blog_word_band_issue(markdown_text, word_limit)
	if not issue:
		return markdown_text
	current_words = pipeline_text_utils.count_words(markdown_text)
	min_words = max(1, word_limit // 2)
	max_words = word_limit * 2
	if logger:
		logger(f"Word-band check failed ({issue}); regenerating once.")
	retry_prompt = (
		"Regenerate this blog post in clean Markdown.\n"
		+ f"Last entry was {current_words} words, but target is {word_limit} words. "
		+ "Please do better on length control.\n"
		+ f"Required hard range: between {min_words} and {max_words} words.\n"
		+ f"Target around {word_limit} words.\n"
		+ "Keep natural paragraph form and factual repository details.\n\n"
		+ source_prompt
	)
	retry_markdown = client.generate(
		prompt=retry_prompt,
		purpose=purpose,
		max_tokens=max_tokens,
	).strip()
	retry_markdown = normalize_markdown_blog(retry_markdown)
	retry_issue = blog_quality_issue(retry_markdown)
	if retry_issue:
		raise RuntimeError(f"blog generation unusable after word-band retry: {retry_issue}")
	band_issue = blog_word_band_issue(retry_markdown, word_limit)
	if band_issue:
		raise RuntimeError(f"blog generation rejected by hard word band: {band_issue}")
	return retry_markdown


#============================================
def generate_blog_markdown_with_llm(
	outline: dict,
	transport_name: str,
	model_override: str,
	max_tokens: int,
	word_limit: int,
	continue_mode: bool,
	repo_draft_cache_dir: str,
	logger=None,
) -> str:
	"""
	Generate Markdown blog body with multi-pass local-llm-wrapper flow.
	"""
	client = create_llm_client(transport_name, model_override, quiet=False)
	repo_buckets = list(outline.get("repo_activity", []))[:8]
	repo_total = len(repo_buckets)
	run_fingerprint = outline_draft_cache.compute_run_fingerprint(
		outline,
		stage_name="blog_repo_draft",
		target_value=word_limit,
		extra={
			"transport_name": transport_name,
			"model_override": model_override or "",
		},
	)

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
			cache_path = outline_draft_cache.build_cache_path(
				repo_draft_cache_dir,
				repo_name,
				run_fingerprint,
			)
			if continue_mode:
				cached = outline_draft_cache.load_cached_draft(cache_path)
				if isinstance(cached, dict):
					cached_markdown = normalize_markdown_blog(str(cached.get("markdown", "")))
					cached_issue = blog_quality_issue(cached_markdown)
					if not cached_issue:
						cached_words = pipeline_text_utils.count_words(cached_markdown)
						if logger:
							logger(
								f"Repo draft {index}/{repo_total} cache hit for {repo_name} "
								+ f"({cached_words} words)."
							)
						candidate_drafts.append(
							{
								"repo_full_name": repo_name,
								"markdown": cached_markdown,
								"word_count": cached_words,
								"score": 1000 - abs(cached_words - repo_word_target),
							}
						)
						continue
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
					+ "Please do better.\n"
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
			outline_draft_cache.save_cached_draft(
				cache_path,
				{
					"repo_full_name": repo_name,
					"repo_index": index,
					"repo_total": repo_total,
					"word_count": repo_words,
					"word_target": repo_word_target,
					"markdown": repo_markdown,
					"generated_at_local": datetime.now().isoformat(),
					"run_fingerprint": run_fingerprint,
				},
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
				+ "Please do better.\n\n"
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
				return enforce_blog_word_band(
					client,
					fallback_retry,
					fallback_prompt,
					word_limit,
					max_tokens,
					logger=logger,
					purpose="daily markdown blog fallback word-band retry",
				)
		return enforce_blog_word_band(
			client,
			fallback,
			fallback_prompt,
			word_limit,
			max_tokens,
			logger=logger,
			purpose="daily markdown blog fallback word-band retry",
		)

	candidate_drafts.sort(key=lambda item: item.get("score", 0), reverse=True)
	best_candidate = candidate_drafts[0]
	min_words = max(1, word_limit // 2)
	use_multi_source_assembly = best_candidate.get("word_count", 0) < min_words
	if logger:
		logger(
			"Selected best repo draft for final assembly: "
			+ f"{best_candidate.get('repo_full_name', '')} "
			+ f"({best_candidate.get('word_count', 0)} words)."
		)
	if use_multi_source_assembly:
		top_candidates = candidate_drafts[: min(4, len(candidate_drafts))]
		final_prompt = build_final_blog_expand_prompt(outline, top_candidates, word_limit)
		if logger:
			logger(
				"Best draft is below lower bound; using multi-draft final assembly prompt."
			)
	else:
		final_prompt = build_final_blog_trim_prompt(outline, best_candidate, word_limit)
	if logger:
		logger(f"Generating final assembly pass (target={word_limit} words).")
	final_markdown = client.generate(
		prompt=final_prompt,
		purpose="daily markdown blog final assembly",
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
			+ "Please do better.\n"
			+ "No reader call-to-action. No blogging advice content.\n\n"
			+ final_prompt
		)
		final_markdown = client.generate(
			prompt=retry_prompt,
			purpose="daily markdown blog final regenerate",
			max_tokens=max_tokens,
		).strip()
		final_markdown = normalize_markdown_blog(final_markdown)
	final_markdown = enforce_blog_word_band(
		client,
		final_markdown,
		final_prompt,
		word_limit,
		max_tokens,
		logger=logger,
		purpose="daily markdown blog final word-band retry",
	)
	if logger:
		final_words = pipeline_text_utils.count_words(final_markdown)
		logger(f"Final assembly output ready ({final_words} words; target={word_limit}).")
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
	user = pipeline_settings.get_github_username(settings, "vosslab")
	default_transport = pipeline_settings.get_enabled_llm_transport(settings)
	default_model = pipeline_settings.get_llm_provider_model(settings, default_transport)
	default_max_tokens = pipeline_settings.get_setting_int(settings, ["llm", "max_tokens"], 1200)
	input_path = pipeline_settings.resolve_user_scoped_out_path(
		args.input,
		DEFAULT_INPUT_PATH,
		user,
	)
	output_path_arg = pipeline_settings.resolve_user_scoped_out_path(
		args.output,
		DEFAULT_OUTPUT_PATH,
		user,
	)
	repo_draft_cache_dir = pipeline_settings.resolve_user_scoped_out_path(
		args.repo_draft_cache_dir,
		DEFAULT_REPO_DRAFT_CACHE_DIR,
		user,
	)
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
		+ f"input={os.path.abspath(input_path)}, output={os.path.abspath(output_path_arg)}, "
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
	outline = load_outline(input_path)
	if not outline_has_activity(outline):
		log_step("No repo commit activity in outline; exiting blog stage without LLM calls.")
		log_step("No blog file written.")
		return
	log_step(
		"Repo draft cache: "
		+ f"dir={os.path.abspath(repo_draft_cache_dir)}, continue={args.continue_mode}"
	)
	log_step("Generating Markdown blog post with incremental drafts and final assembly pass.")
	try:
		markdown = generate_blog_markdown_with_llm(
			outline,
			transport_name=transport_name,
			model_override=model_override,
			max_tokens=max_tokens,
			word_limit=args.word_limit,
			continue_mode=args.continue_mode,
			repo_draft_cache_dir=os.path.abspath(repo_draft_cache_dir),
			logger=log_step,
		)
	except RuntimeError as error:
		log_step(f"Blog generation failed: {error}")
		log_step("No blog file written.")
		return
	date_text = local_date_stamp()
	dated_output = date_stamp_output_path(output_path_arg, date_text)
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


if __name__ == "__main__":
	main()
