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


WHITESPACE_RE = re.compile(r"\s+")
DATE_STAMP_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
DEFAULT_INPUT_PATH = "out/outline.json"
DEFAULT_OUTPUT_PATH = "out/bluesky_post.txt"
DEFAULT_REPO_DRAFT_CACHE_DIR = "out/bluesky_repo_drafts"


#============================================
def log_step(message: str) -> None:
	"""
	Print one timestamped progress line.
	"""
	now_text = datetime.now().strftime("%H:%M:%S")
	print(f"[outline_to_bluesky_post {now_text}] {message}", flush=True)


#============================================
def parse_args() -> argparse.Namespace:
	"""
	Parse command-line arguments.
	"""
	parser = argparse.ArgumentParser(
		description="Render a target-length Bluesky post from outline JSON."
	)
	parser.add_argument(
		"--input",
		default=DEFAULT_INPUT_PATH,
		help="Path to outline JSON input.",
	)
	parser.add_argument(
		"--output",
		default=DEFAULT_OUTPUT_PATH,
		help="Path to output text file.",
	)
	parser.add_argument(
		"--char-limit",
		type=int,
		default=140,
		help="Target character count for Bluesky text.",
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
		help="Directory for per-repo intermediate Bluesky draft cache files.",
	)
	parser.add_argument(
		"--continue",
		dest="continue_mode",
		action="store_true",
		help="Reuse cached per-repo Bluesky drafts when available (default: enabled).",
	)
	parser.add_argument(
		"--no-continue",
		dest="continue_mode",
		action="store_false",
		help="Disable per-repo Bluesky draft cache reuse.",
	)
	parser.set_defaults(continue_mode=True)
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
def local_date_stamp() -> str:
	"""
	Return local-date stamp for filenames.
	"""
	return datetime.now().astimezone().strftime("%Y-%m-%d")


#============================================
def date_stamp_output_path(output_path: str, date_text: str) -> str:
	"""
	Ensure Bluesky output filename includes one local-date stamp.
	"""
	candidate = (output_path or "").strip() or DEFAULT_OUTPUT_PATH
	candidate = candidate.replace("{date}", date_text)
	directory, filename = os.path.split(candidate)
	if not filename:
		filename = "bluesky_post.txt"
	stem, extension = os.path.splitext(filename)
	if not extension:
		extension = ".txt"
	if DATE_STAMP_RE.search(filename):
		dated_filename = filename
	else:
		dated_filename = f"{stem}-{date_text}{extension}"
	return os.path.join(directory, dated_filename)


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
def describe_llm_execution_path(transport_name: str, model_override: str) -> str:
	"""
	Describe configured LLM transport execution order.
	"""
	return outline_llm.describe_llm_execution_path(transport_name, model_override)


#============================================
def create_llm_client(transport_name: str, model_override: str, quiet: bool) -> object:
	"""
	Create local-llm-wrapper client for Bluesky generation.
	"""
	return outline_llm.create_llm_client(
		__file__,
		transport_name,
		model_override,
		quiet,
	)


#============================================
def build_bluesky_text(outline: dict) -> str:
	"""
	Build one short fallback social post from outline data.
	"""
	user = outline.get("user", "unknown")
	totals = outline.get("totals", {})
	repos = outline.get("repo_activity", [])
	repo_label = "n/a"
	if repos:
		repo_label = repos[0].get("repo_name") or repos[0].get("repo_full_name") or "n/a"

	text = (
		f"{user} daily GitHub: {totals.get('commit_records', 0)} commits, "
		f"{totals.get('pull_request_records', 0)} PRs, "
		f"{totals.get('issue_records', 0)} issues. Top repo: {repo_label}."
	)
	return text


#============================================
def compute_repo_pass_char_target(repo_count: int, char_limit: int) -> int:
	"""
	Compute per-repo character target using blog-like heuristic.
	"""
	return outline_llm.compute_incremental_target(repo_count, char_limit, 100)


#============================================
def normalize_bluesky_text(text: str) -> str:
	"""
	Normalize LLM text into one clean Bluesky-ready line.
	"""
	clean = (text or "").strip()
	if not clean:
		return ""
	clean = clean.replace("*", " ")
	clean = WHITESPACE_RE.sub(" ", clean).strip()
	return clean


#============================================
def bluesky_quality_issue(text: str) -> str:
	"""
	Return a validation issue string when Bluesky text is unusable.
	"""
	clean = (text or "").strip()
	if not clean:
		return "empty output"
	lower = clean.lower()
	if ("error_code" in lower) or ("generationerror" in lower):
		return "llm returned error payload"
	if clean.startswith("{") and clean.endswith("}"):
		return "llm returned structured error/object text"
	return ""


#============================================
def build_repo_bluesky_prompt(
	outline: dict,
	repo_bucket: dict,
	repo_index: int,
	repo_total: int,
	char_target: int,
) -> str:
	"""
	Build one repo-focused Bluesky prompt for incremental generation.
	"""
	context = {
		"user": outline.get("user", "unknown"),
		"window_start": outline.get("window_start", ""),
		"window_end": outline.get("window_end", ""),
		"totals": outline.get("totals", {}),
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
			"commit_messages": list(repo_bucket.get("commit_messages", []))[:8],
			"issue_titles": list(repo_bucket.get("issue_titles", []))[:6],
			"pull_request_titles": list(repo_bucket.get("pull_request_titles", []))[:6],
		},
	}
	context_json = json.dumps(context, ensure_ascii=True, indent=2)
	return (
		"You are writing one Bluesky post candidate about a daily engineering update.\n"
		f"Focus on repo {repo_index} of {repo_total}.\n"
		f"Target length: about {char_target} characters.\n"
		"Rules:\n"
		"- Output plain text only on one line.\n"
		"- Mention the repository name exactly as provided.\n"
		"- Include concrete activity counts from the data.\n"
		"- No hashtags, no emojis, no call-to-action.\n"
		"- No meta commentary about writing.\n\n"
		"Context JSON:\n"
		f"{context_json}\n"
	)


#============================================
def build_bluesky_fallback_prompt(outline: dict, char_limit: int) -> str:
	"""
	Build single-pass fallback prompt using broad outline context.
	"""
	repos = []
	for bucket in list(outline.get("repo_activity", []))[:6]:
		repos.append(
			{
				"repo_full_name": bucket.get("repo_full_name", ""),
				"commit_count": bucket.get("commit_count", 0),
				"issue_count": bucket.get("issue_count", 0),
				"pull_request_count": bucket.get("pull_request_count", 0),
			}
		)
	context = {
		"user": outline.get("user", "unknown"),
		"window_start": outline.get("window_start", ""),
		"window_end": outline.get("window_end", ""),
		"totals": outline.get("totals", {}),
		"repos": repos,
	}
	context_json = json.dumps(context, ensure_ascii=True, indent=2)
	return (
		"You are writing a daily engineering Bluesky post.\n"
		f"Target length: about {char_limit} characters.\n"
		"Rules:\n"
		"- Output plain text only on one line.\n"
		"- Include at least one repository name and concrete counts.\n"
		"- No hashtags, no emojis, no call-to-action.\n\n"
		"Context JSON:\n"
		f"{context_json}\n"
	)


#============================================
def build_final_bluesky_trim_prompt(outline: dict, best_draft: dict, char_limit: int) -> str:
	"""
	Build final trim prompt from best incremental draft.
	"""
	context = {
		"user": outline.get("user", "unknown"),
		"window_start": outline.get("window_start", ""),
		"window_end": outline.get("window_end", ""),
		"totals": outline.get("totals", {}),
		"selected_repo_full_name": best_draft.get("repo_full_name", ""),
		"selected_draft_char_count": best_draft.get("char_count", 0),
		"selected_draft_text": best_draft.get("text", ""),
	}
	context_json = json.dumps(context, ensure_ascii=True, indent=2)
	return (
		"You are revising one Bluesky post draft.\n"
		f"Target length: about {char_limit} characters.\n"
		"Keep the strongest facts and wording, but pare it down to target length.\n"
		"Rules:\n"
		"- Output plain text only on one line.\n"
		"- Keep repository names and concrete counts factual.\n"
		"- No hashtags, no emojis, no call-to-action.\n\n"
		"Context JSON:\n"
		f"{context_json}\n"
	)


#============================================
def generate_bluesky_text_with_llm(
	outline: dict,
	transport_name: str,
	model_override: str,
	max_tokens: int,
	char_limit: int,
	continue_mode: bool,
	repo_draft_cache_dir: str,
	logger=None,
) -> str:
	"""
	Generate Bluesky text with incremental repo drafts and final trim pass.
	"""
	client = create_llm_client(transport_name, model_override, quiet=False)
	repo_buckets = list(outline.get("repo_activity", []))[:8]
	repo_total = len(repo_buckets)
	candidates: list[dict] = []
	run_fingerprint = outline_draft_cache.compute_run_fingerprint(
		outline,
		stage_name="bluesky_repo_draft",
		target_value=char_limit,
		extra={
			"transport_name": transport_name,
			"model_override": model_override or "",
		},
	)

	if repo_total > 0:
		char_target = compute_repo_pass_char_target(repo_total, char_limit)
		if logger:
			logger(
				"Running incremental repo drafts: "
				+ f"{repo_total} draft(s), per-repo target={char_target} chars."
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
					cached_text = normalize_bluesky_text(str(cached.get("text", "")))
					cached_issue = bluesky_quality_issue(cached_text)
					if not cached_issue:
						cached_chars = len(cached_text)
						if logger:
							logger(
								f"Repo draft {index}/{repo_total} cache hit for {repo_name} "
								+ f"({cached_chars} chars)."
							)
						candidates.append(
							{
								"repo_full_name": repo_name,
								"text": cached_text,
								"char_count": cached_chars,
								"score": 1000 - abs(cached_chars - char_target),
							}
						)
						continue
			if logger:
				logger(
					f"Generating repo draft {index}/{repo_total} for {repo_name} "
					+ f"(target={char_target} chars)."
				)
			prompt = build_repo_bluesky_prompt(
				outline,
				repo_bucket,
				index,
				repo_total,
				char_target,
			)
			text = client.generate(
				prompt=prompt,
				purpose=f"bluesky repo draft {index} of {repo_total}",
				max_tokens=max_tokens,
			).strip()
			text = normalize_bluesky_text(text)
			issue = bluesky_quality_issue(text)
			if issue:
				if logger:
					logger(f"Repo draft {index}/{repo_total} flagged ({issue}); retrying once.")
				retry_prompt = (
					"Regenerate this Bluesky draft as one clean plain-text line.\n"
					+ f"Target around {char_target} characters.\n"
					+ "Please do better.\n"
					+ "No hashtags. No emojis. No call-to-action.\n\n"
					+ prompt
				)
				text = client.generate(
					prompt=retry_prompt,
					purpose=f"bluesky repo draft regenerate {index} of {repo_total}",
					max_tokens=max_tokens,
				).strip()
				text = normalize_bluesky_text(text)
				issue = bluesky_quality_issue(text)
			if issue:
				if logger:
					logger(f"Repo draft {index}/{repo_total} skipped after retry ({issue}).")
				continue
			char_count = len(text)
			if logger:
				logger(f"Repo draft {index}/{repo_total} accepted ({char_count} chars).")
			outline_draft_cache.save_cached_draft(
				cache_path,
				{
					"repo_full_name": repo_name,
					"repo_index": index,
					"repo_total": repo_total,
					"char_count": char_count,
					"char_target": char_target,
					"text": text,
					"generated_at_local": datetime.now().isoformat(),
					"run_fingerprint": run_fingerprint,
				},
			)
			candidates.append(
				{
					"repo_full_name": repo_name,
					"text": text,
					"char_count": char_count,
					"score": 1000 - abs(char_count - char_target),
				}
			)

	if not candidates:
		if logger:
			logger("No valid repo drafts; running single-pass fallback Bluesky generation.")
		fallback_prompt = build_bluesky_fallback_prompt(outline, char_limit)
		fallback = client.generate(
			prompt=fallback_prompt,
			purpose="bluesky fallback",
			max_tokens=max_tokens,
		).strip()
		fallback = normalize_bluesky_text(fallback)
		issue = bluesky_quality_issue(fallback)
		if issue:
			if logger:
				logger(f"Fallback draft flagged ({issue}); retrying once.")
			retry_prompt = (
				"Regenerate as one clean plain-text line.\n"
				+ f"Target around {char_limit} characters.\n\n"
				+ "Please do better.\n\n"
				+ fallback_prompt
			)
			retry_text = client.generate(
				prompt=retry_prompt,
				purpose="bluesky fallback regenerate",
				max_tokens=max_tokens,
			).strip()
			retry_text = normalize_bluesky_text(retry_text)
			if retry_text:
				return retry_text
		return fallback

	candidates.sort(key=lambda item: item.get("score", 0), reverse=True)
	best_candidate = candidates[0]
	if logger:
		logger(
			"Selected best repo draft for final trim: "
			+ f"{best_candidate.get('repo_full_name', '')} "
			+ f"({best_candidate.get('char_count', 0)} chars)."
		)
	final_prompt = build_final_bluesky_trim_prompt(outline, best_candidate, char_limit)
	if logger:
		logger(f"Generating final trim pass (target={char_limit} chars).")
	final_text = client.generate(
		prompt=final_prompt,
		purpose="bluesky final trim",
		max_tokens=max_tokens,
	).strip()
	final_text = normalize_bluesky_text(final_text)
	final_issue = bluesky_quality_issue(final_text)
	if final_issue:
		if logger:
			logger(f"Final trim output flagged ({final_issue}); retrying once.")
		retry_prompt = (
			"Regenerate final Bluesky text as one plain line.\n"
			+ f"Target around {char_limit} characters.\n"
			+ "Please do better.\n"
			+ "No hashtags. No emojis. No call-to-action.\n\n"
			+ final_prompt
		)
		final_text = client.generate(
			prompt=retry_prompt,
			purpose="bluesky final regenerate",
			max_tokens=max_tokens,
		).strip()
		final_text = normalize_bluesky_text(final_text)
	if logger:
		logger(f"Final trim output ready ({len(final_text)} chars; target={char_limit}).")
	return final_text


#============================================
def main() -> None:
	"""
	Generate Bluesky text with LLM using target character count.
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
	if args.char_limit < 1:
		raise RuntimeError("char-limit must be >= 1")

	log_step(
		"Starting bluesky stage with "
		+ f"input={os.path.abspath(input_path)}, output={os.path.abspath(output_path_arg)}, "
		+ f"char_limit={args.char_limit}"
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
		log_step("No repo commit activity in outline; exiting bluesky stage without LLM calls.")
		log_step("No Bluesky file written.")
		return
	log_step(
		"Repo draft cache: "
		+ f"dir={os.path.abspath(repo_draft_cache_dir)}, continue={args.continue_mode}"
	)
	log_step("Generating Bluesky text with incremental drafts and final trim pass.")
	try:
		text = generate_bluesky_text_with_llm(
			outline,
			transport_name=transport_name,
			model_override=model_override,
			max_tokens=max_tokens,
			char_limit=args.char_limit,
			continue_mode=args.continue_mode,
			repo_draft_cache_dir=os.path.abspath(repo_draft_cache_dir),
			logger=log_step,
		)
	except RuntimeError as error:
		log_step(f"LLM generation failed ({error}); using deterministic fallback text.")
		text = build_bluesky_text(outline)

	final_text = pipeline_text_utils.trim_to_char_limit(text, args.char_limit)
	if len(final_text) < len(text):
		log_step(
			"Trimmed final text to char limit for publish safety "
			+ f"({len(text)} -> {len(final_text)} chars)."
		)
	pipeline_text_utils.assert_char_limit(final_text, args.char_limit)

	date_text = local_date_stamp()
	dated_output = date_stamp_output_path(output_path_arg, date_text)
	output_path = os.path.abspath(dated_output)
	os.makedirs(os.path.dirname(output_path), exist_ok=True)
	log_step(f"Using local date stamp for Bluesky filename: {date_text}")
	log_step(f"Writing Bluesky output to {output_path}")
	with open(output_path, "w", encoding="utf-8") as handle:
		handle.write(final_text)
		handle.write("\n")

	log_step(f"Wrote {output_path} ({len(final_text)} chars; target={args.char_limit})")


if __name__ == "__main__":
	main()
