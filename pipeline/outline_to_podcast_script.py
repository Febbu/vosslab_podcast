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
SPEAKER_LINE_RE = re.compile(r"^\s*([A-Za-z0-9_ -]+)\s*:\s*(.+?)\s*$")
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


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
		description="Render a target-length N-speaker podcast script from outline JSON."
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
		help="Target total words for spoken text.",
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
		default="out/podcast_repo_drafts",
		help="Directory for per-repo intermediate podcast draft cache files.",
	)
	parser.add_argument(
		"--continue",
		dest="continue_mode",
		action="store_true",
		help="Reuse cached per-repo podcast drafts when available (default: enabled).",
	)
	parser.add_argument(
		"--no-continue",
		dest="continue_mode",
		action="store_false",
		help="Disable per-repo podcast draft cache reuse.",
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
def describe_llm_execution_path(transport_name: str, model_override: str) -> str:
	"""
	Describe configured LLM transport execution order.
	"""
	return outline_llm.describe_llm_execution_path(transport_name, model_override)


#============================================
def create_llm_client(transport_name: str, model_override: str, quiet: bool) -> object:
	"""
	Create local-llm-wrapper client for podcast generation.
	"""
	return outline_llm.create_llm_client(
		__file__,
		transport_name,
		model_override,
		quiet,
	)


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
	Build ordered deterministic fallback speaker lines.
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
			f"Welcome to the daily {user} GitHub report for {window_start} to {window_end}.",
		)
	)

	for index, label in enumerate(speaker_labels[1:], start=2):
		lines.append(
			(
				label,
				f"I am speaker {index}, and I will cover part of today's engineering activity.",
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
			"That closes the daily summary. We will return with the next GitHub activity report.",
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
def compute_repo_pass_word_target(repo_count: int, word_limit: int) -> int:
	"""
	Compute per-repo generation target using blog-like heuristic.
	"""
	return outline_llm.compute_incremental_target(repo_count, word_limit, 100)


#============================================
def normalize_spoken_text(text: str) -> str:
	"""
	Normalize one spoken segment from model output.
	"""
	clean = (text or "").strip()
	if not clean:
		return ""
	clean = clean.replace("\n", " ")
	clean = clean.lstrip("-*# ").strip()
	clean = WHITESPACE_RE.sub(" ", clean).strip()
	return clean


#============================================
def normalize_speaker_token(token: str) -> str:
	"""
	Normalize a speaker token like "speaker 1" to "SPEAKER_1".
	"""
	normalized = re.sub(r"[^A-Za-z0-9]+", "_", (token or "").strip().upper()).strip("_")
	if re.fullmatch(r"SPEAKER\d+", normalized):
		normalized = f"SPEAKER_{normalized[len('SPEAKER'):]}"
	return normalized


#============================================
def split_sentences(text: str) -> list[str]:
	"""
	Split one narrative block into sentence-like chunks.
	"""
	clean = normalize_spoken_text(text)
	if not clean:
		return []
	parts = SENTENCE_SPLIT_RE.split(clean)
	sentences = []
	for part in parts:
		item = normalize_spoken_text(part)
		if item:
			sentences.append(item)
	if not sentences:
		return [clean]
	return sentences


#============================================
def parse_generated_script_lines(
	script_text: str,
	speaker_labels: list[str],
) -> list[tuple[str, str]]:
	"""
	Parse LLM output into speaker-labeled lines with narrative salvage fallback.
	"""
	allowed = set(speaker_labels)
	parsed: list[tuple[str, str]] = []
	narrative_parts: list[str] = []
	for raw_line in (script_text or "").splitlines():
		line = raw_line.strip()
		if not line:
			continue
		match = SPEAKER_LINE_RE.match(line)
		if not match:
			narrative_parts.append(line)
			continue
		speaker = normalize_speaker_token(match.group(1))
		text = normalize_spoken_text(match.group(2))
		if (speaker in allowed) and text:
			parsed.append((speaker, text))
			continue
		narrative_parts.append(line)
	if narrative_parts:
		joined = " ".join(narrative_parts)
		for index, sentence in enumerate(split_sentences(joined)):
			speaker = speaker_labels[index % len(speaker_labels)]
			parsed.append((speaker, sentence))
	return parsed


#============================================
def ensure_required_speakers(
	lines: list[tuple[str, str]],
	speaker_labels: list[str],
) -> list[tuple[str, str]]:
	"""
	Ensure every configured speaker appears at least once.
	"""
	cleaned: list[tuple[str, str]] = []
	for speaker, text in lines:
		spoken = normalize_spoken_text(text)
		if not spoken:
			continue
		cleaned.append((speaker, spoken))
	if not cleaned:
		for speaker in speaker_labels:
			cleaned.append((speaker, "Daily engineering update in progress."))
		return cleaned
	used = {speaker for speaker, _ in cleaned}
	for speaker in speaker_labels:
		if speaker in used:
			continue
		cleaned.append(
			(
				speaker,
				"Quick take: this repo shows steady engineering movement today.",
			)
		)
	return cleaned


#============================================
def podcast_quality_issue(script_text: str) -> str:
	"""
	Return a validation issue string when raw script output is unusable.
	"""
	clean = (script_text or "").strip()
	if not clean:
		return "empty output"
	lower = clean.lower()
	if ("error_code" in lower) or ("generationerror" in lower):
		return "llm returned error payload"
	if clean.startswith("{") and clean.endswith("}"):
		return "llm returned structured error/object text"
	return ""


#============================================
def build_repo_podcast_prompt(
	outline: dict,
	repo_bucket: dict,
	repo_index: int,
	repo_total: int,
	speaker_labels: list[str],
	word_target: int,
) -> str:
	"""
	Build one repo-focused podcast draft prompt.
	"""
	context = {
		"user": outline.get("user", "unknown"),
		"window_start": outline.get("window_start", ""),
		"window_end": outline.get("window_end", ""),
		"totals": outline.get("totals", {}),
		"repo_index": repo_index,
		"repo_total": repo_total,
		"speaker_labels": speaker_labels,
		"repo": {
			"repo_full_name": repo_bucket.get("repo_full_name", ""),
			"description": repo_bucket.get("description", ""),
			"language": repo_bucket.get("language", ""),
			"commit_count": repo_bucket.get("commit_count", 0),
			"issue_count": repo_bucket.get("issue_count", 0),
			"pull_request_count": repo_bucket.get("pull_request_count", 0),
			"latest_event_time": repo_bucket.get("latest_event_time", ""),
			"commit_messages": list(repo_bucket.get("commit_messages", []))[:8],
			"issue_titles": list(repo_bucket.get("issue_titles", []))[:8],
			"pull_request_titles": list(repo_bucket.get("pull_request_titles", []))[:8],
		},
	}
	context_json = json.dumps(context, ensure_ascii=True, indent=2)
	return (
		"You are writing one podcast-script candidate for a daily engineering update.\n"
		f"This candidate must focus on repo {repo_index} of {repo_total}.\n"
		f"Target length: about {word_target} words.\n"
		"Output format rules:\n"
		"- Plain text lines only in this format: SPEAKER_X: spoken text\n"
		"- Use only speaker labels listed in context.\n"
		"- Mention repository names and activity counts exactly from data.\n"
		"- No stage directions, no call-to-action, no meta-writing advice.\n\n"
		"Context JSON:\n"
		f"{context_json}\n"
	)


#============================================
def build_podcast_fallback_prompt(
	outline: dict,
	speaker_labels: list[str],
	word_limit: int,
) -> str:
	"""
	Build broad fallback prompt when repo drafts fail.
	"""
	repos = []
	for bucket in list(outline.get("repo_activity", []))[:8]:
		repos.append(
			{
				"repo_full_name": bucket.get("repo_full_name", ""),
				"commit_count": bucket.get("commit_count", 0),
				"issue_count": bucket.get("issue_count", 0),
				"pull_request_count": bucket.get("pull_request_count", 0),
				"description": bucket.get("description", ""),
			}
		)
	context = {
		"user": outline.get("user", "unknown"),
		"window_start": outline.get("window_start", ""),
		"window_end": outline.get("window_end", ""),
		"totals": outline.get("totals", {}),
		"speaker_labels": speaker_labels,
		"repos": repos,
	}
	context_json = json.dumps(context, ensure_ascii=True, indent=2)
	return (
		"You are writing a daily engineering podcast script.\n"
		f"Target length: about {word_limit} words.\n"
		"Output format rules:\n"
		"- Plain text lines only in this format: SPEAKER_X: spoken text\n"
		"- Use only speaker labels listed in context.\n"
		"- Mention concrete counts and repo names from context.\n"
		"- No stage directions and no call-to-action.\n\n"
		"Context JSON:\n"
		f"{context_json}\n"
	)


#============================================
def build_final_podcast_trim_prompt(
	outline: dict,
	best_candidate: dict,
	speaker_labels: list[str],
	word_limit: int,
) -> str:
	"""
	Build final trim prompt from the best incremental draft.
	"""
	context = {
		"user": outline.get("user", "unknown"),
		"window_start": outline.get("window_start", ""),
		"window_end": outline.get("window_end", ""),
		"totals": outline.get("totals", {}),
		"speaker_labels": speaker_labels,
		"selected_repo_full_name": best_candidate.get("repo_full_name", ""),
		"selected_draft_word_count": best_candidate.get("word_count", 0),
		"selected_draft_script": best_candidate.get("script_text", ""),
	}
	context_json = json.dumps(context, ensure_ascii=True, indent=2)
	return (
		"You are revising one podcast script draft.\n"
		f"Target length: about {word_limit} words.\n"
		"Keep the strongest factual details and make the dialogue sound natural.\n"
		"Output format rules:\n"
		"- Plain text lines only in this format: SPEAKER_X: spoken text\n"
		"- Use only speaker labels listed in context.\n"
		"- No stage directions and no call-to-action.\n\n"
		"Context JSON:\n"
		f"{context_json}\n"
	)


#============================================
def generate_podcast_lines_with_llm(
	outline: dict,
	speaker_labels: list[str],
	transport_name: str,
	model_override: str,
	max_tokens: int,
	word_limit: int,
	continue_mode: bool,
	repo_draft_cache_dir: str,
	logger=None,
) -> list[tuple[str, str]]:
	"""
	Generate podcast lines with incremental repo drafts and final trim pass.
	"""
	client = create_llm_client(transport_name, model_override, quiet=False)
	repo_buckets = list(outline.get("repo_activity", []))[:8]
	repo_total = len(repo_buckets)
	candidates: list[dict] = []
	run_fingerprint = outline_draft_cache.compute_run_fingerprint(
		outline,
		stage_name="podcast_repo_draft",
		target_value=word_limit,
		extra={
			"transport_name": transport_name,
			"model_override": model_override or "",
			"speaker_labels": speaker_labels,
		},
	)

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
					cached_lines = parse_generated_script_lines(
						str(cached.get("script_text", "")),
						speaker_labels,
					)
					cached_lines = ensure_required_speakers(cached_lines, speaker_labels)
					cached_words = count_script_words(cached_lines)
					if cached_words > 0:
						if logger:
							logger(
								f"Repo draft {index}/{repo_total} cache hit for {repo_name} "
								+ f"({cached_words} words)."
							)
						candidates.append(
							{
								"repo_full_name": repo_name,
								"lines": cached_lines,
								"script_text": render_script_text(cached_lines),
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
			prompt = build_repo_podcast_prompt(
				outline,
				repo_bucket,
				index,
				repo_total,
				speaker_labels,
				repo_word_target,
			)
			raw_text = client.generate(
				prompt=prompt,
				purpose=f"podcast repo draft {index} of {repo_total}",
				max_tokens=max_tokens,
			).strip()
			issue = podcast_quality_issue(raw_text)
			if issue:
				if logger:
					logger(f"Repo draft {index}/{repo_total} flagged ({issue}); retrying once.")
				retry_prompt = (
					"Regenerate this podcast draft as clean speaker lines.\n"
					+ f"Target around {repo_word_target} words.\n"
					+ "Please do better.\n"
					+ "Format each line as SPEAKER_X: text.\n\n"
					+ prompt
				)
				raw_text = client.generate(
					prompt=retry_prompt,
					purpose=f"podcast repo draft regenerate {index} of {repo_total}",
					max_tokens=max_tokens,
				).strip()
				issue = podcast_quality_issue(raw_text)
			if issue:
				if logger:
					logger(f"Repo draft {index}/{repo_total} skipped after retry ({issue}).")
				continue
			lines = parse_generated_script_lines(raw_text, speaker_labels)
			lines = ensure_required_speakers(lines, speaker_labels)
			word_count = count_script_words(lines)
			if word_count < 1:
				if logger:
					logger(f"Repo draft {index}/{repo_total} skipped (no usable spoken text).")
				continue
			if logger:
				logger(f"Repo draft {index}/{repo_total} accepted ({word_count} words).")
			script_text = render_script_text(lines)
			outline_draft_cache.save_cached_draft(
				cache_path,
				{
					"repo_full_name": repo_name,
					"repo_index": index,
					"repo_total": repo_total,
					"word_count": word_count,
					"word_target": repo_word_target,
					"script_text": script_text,
					"generated_at_local": datetime.now().isoformat(),
					"run_fingerprint": run_fingerprint,
				},
			)
			candidates.append(
				{
					"repo_full_name": repo_name,
					"lines": lines,
					"script_text": script_text,
					"word_count": word_count,
					"score": 1000 - abs(word_count - repo_word_target),
				}
			)

	if not candidates:
		if logger:
			logger("No valid repo drafts; running single-pass fallback podcast generation.")
		fallback_prompt = build_podcast_fallback_prompt(outline, speaker_labels, word_limit)
		fallback_raw = client.generate(
			prompt=fallback_prompt,
			purpose="podcast fallback",
			max_tokens=max_tokens,
		).strip()
		issue = podcast_quality_issue(fallback_raw)
		if issue:
			if logger:
				logger(f"Fallback draft flagged ({issue}); retrying once.")
			retry_prompt = (
				"Regenerate as speaker lines using format SPEAKER_X: text.\n"
				+ f"Target around {word_limit} words.\n\n"
				+ "Please do better.\n\n"
				+ fallback_prompt
			)
			fallback_raw = client.generate(
				prompt=retry_prompt,
				purpose="podcast fallback regenerate",
				max_tokens=max_tokens,
			).strip()
		lines = parse_generated_script_lines(fallback_raw, speaker_labels)
		lines = ensure_required_speakers(lines, speaker_labels)
		if not lines:
			lines = build_podcast_lines(outline, speaker_labels)
		return trim_lines_to_word_limit(lines, word_limit)

	candidates.sort(key=lambda item: item.get("score", 0), reverse=True)
	best_candidate = candidates[0]
	if logger:
		logger(
			"Selected best repo draft for final trim: "
			+ f"{best_candidate.get('repo_full_name', '')} "
			+ f"({best_candidate.get('word_count', 0)} words)."
		)
	final_prompt = build_final_podcast_trim_prompt(
		outline,
		best_candidate,
		speaker_labels,
		word_limit,
	)
	if logger:
		logger(f"Generating final trim pass (target={word_limit} words).")
	final_raw = client.generate(
		prompt=final_prompt,
		purpose="podcast final trim",
		max_tokens=max_tokens,
	).strip()
	final_issue = podcast_quality_issue(final_raw)
	if final_issue:
		if logger:
			logger(f"Final trim output flagged ({final_issue}); retrying once.")
		retry_prompt = (
			"Regenerate final podcast script as speaker lines.\n"
			+ f"Target around {word_limit} words.\n"
			+ "Please do better.\n"
			+ "Format each line as SPEAKER_X: text.\n\n"
			+ final_prompt
		)
		final_raw = client.generate(
			prompt=retry_prompt,
			purpose="podcast final regenerate",
			max_tokens=max_tokens,
		).strip()

	final_lines = parse_generated_script_lines(final_raw, speaker_labels)
	if not final_lines:
		final_lines = list(best_candidate.get("lines", []))
	final_lines = ensure_required_speakers(final_lines, speaker_labels)
	untrimmed_words = count_script_words(final_lines)
	trimmed_lines = trim_lines_to_word_limit(final_lines, word_limit)
	trimmed_words = count_script_words(trimmed_lines)
	if logger:
		logger(
			"Final trim output ready "
			+ f"({trimmed_words} words; target={word_limit}; pre-trim={untrimmed_words})."
		)
	return trimmed_lines


#============================================
def main() -> None:
	"""
	Generate N-speaker podcast script with LLM using target word count.
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
		"Starting podcast script stage with "
		+ f"input={os.path.abspath(args.input)}, output={os.path.abspath(args.output)}, "
		+ f"num_speakers={args.num_speakers}, word_limit={args.word_limit}"
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
	log_step("Building speaker label set.")
	speaker_labels = build_speaker_labels(args.num_speakers)
	log_step(
		"Repo draft cache: "
		+ f"dir={os.path.abspath(args.repo_draft_cache_dir)}, continue={args.continue_mode}"
	)
	log_step("Generating podcast script with incremental drafts and final trim pass.")
	try:
		lines = generate_podcast_lines_with_llm(
			outline,
			speaker_labels=speaker_labels,
			transport_name=transport_name,
			model_override=model_override,
			max_tokens=max_tokens,
			word_limit=args.word_limit,
			continue_mode=args.continue_mode,
			repo_draft_cache_dir=os.path.abspath(args.repo_draft_cache_dir),
			logger=log_step,
		)
	except RuntimeError as error:
		log_step(f"LLM generation failed ({error}); using deterministic fallback script.")
		lines = build_podcast_lines(outline, speaker_labels)

	lines = ensure_required_speakers(lines, speaker_labels)
	trimmed_lines = trim_lines_to_word_limit(lines, args.word_limit)
	spoken_word_count = count_script_words(trimmed_lines)
	used_speakers = {speaker for speaker, _text in trimmed_lines}
	if len(used_speakers) < len(speaker_labels):
		log_step("Speaker coverage dropped after trim; restoring missing speakers.")
		trimmed_lines = ensure_required_speakers(trimmed_lines, speaker_labels)
		trimmed_lines = trim_lines_to_word_limit(trimmed_lines, args.word_limit)
		spoken_word_count = count_script_words(trimmed_lines)

	output_path = os.path.abspath(args.output)
	output_dir = os.path.dirname(output_path)
	if output_dir:
		os.makedirs(output_dir, exist_ok=True)
	script_text = render_script_text(trimmed_lines)
	log_step(f"Writing podcast script output to {output_path}")
	with open(output_path, "w", encoding="utf-8") as handle:
		handle.write(script_text)

	log_step(
		f"Wrote {output_path} "
		f"({spoken_word_count} words, {args.num_speakers} speakers; target={args.word_limit})"
	)


if __name__ == "__main__":
	main()
