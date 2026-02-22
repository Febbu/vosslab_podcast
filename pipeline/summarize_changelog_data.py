#!/usr/bin/env python3
"""Summarize long changelog entries in fetch JSONL via LLM.

Reads the fetch-stage JSONL, finds repo_changelog records with long
latest_entry fields, summarizes them using changelog_summarizer, and
writes the updated JSONL back in place. Short entries and non-changelog
records pass through unchanged. Supports depth-based multi-draft
generation via depth_orchestrator.
"""

# Standard Library
import argparse
import json
import os
import random
import re
import tempfile
from datetime import datetime

# local repo modules
from podlib import depth_orchestrator
from podlib import outline_llm
from podlib import pipeline_settings

from podlib import changelog_summarizer
from podlib import prompt_loader


DEFAULT_INPUT_PATH = "out/github_data.jsonl"
DEFAULT_THRESHOLD = 6000


#============================================
def log_step(message: str) -> None:
	"""
	Print one timestamped progress line.
	"""
	now_text = datetime.now().strftime("%H:%M:%S")
	print(f"[summarize_changelog_data {now_text}] {message}", flush=True)


#============================================
def parse_args() -> argparse.Namespace:
	"""
	Parse command-line arguments.
	"""
	parser = argparse.ArgumentParser(
		description="Summarize long changelog entries in fetch JSONL via LLM."
	)
	parser.add_argument(
		'-i', '--input', dest='input_file',
		default=DEFAULT_INPUT_PATH,
		help="Path to input JSONL from fetch_github_data.py.",
	)
	parser.add_argument(
		'--settings', dest='settings',
		default="settings.yaml",
		help="YAML settings path for LLM defaults.",
	)
	parser.add_argument(
		'--llm-transport', dest='llm_transport',
		choices=["ollama", "apple", "auto"],
		default=None,
		help="local-llm-wrapper transport selection (defaults from settings.yaml).",
	)
	parser.add_argument(
		'--llm-model', dest='llm_model',
		default=None,
		help="Optional model override (defaults from settings.yaml).",
	)
	parser.add_argument(
		'-t', '--threshold', dest='threshold',
		type=int,
		default=DEFAULT_THRESHOLD,
		help="Character threshold for changelog summarization (default: 6000).",
	)
	parser.add_argument(
		'-c', '--chunk-size', dest='chunk_size',
		type=int,
		default=2250,
		help="Characters per chunk for splitting long entries (default: 2250).",
	)
	parser.add_argument(
		'--chunk-overlap', dest='chunk_overlap',
		type=int,
		default=250,
		help="Overlap between consecutive chunks (default: 250).",
	)
	parser.add_argument(
		'-d', '--depth', dest='depth',
		type=int,
		default=None,
		help="LLM generation depth 1-4 (higher = more candidates, better quality).",
	)
	# continue / no-continue flag pair
	parser.add_argument(
		'--continue', dest='continue_mode',
		action='store_true',
		help="Reuse cached LLM drafts when available (default).",
	)
	parser.add_argument(
		'--no-continue', dest='continue_mode',
		action='store_false',
		help="Regenerate all LLM outputs from scratch.",
	)
	parser.set_defaults(continue_mode=True)
	parser.add_argument(
		'--llm-max-tokens', dest='llm_max_tokens',
		type=int,
		default=None,
		help="Max generation tokens per LLM call (defaults from settings.yaml).",
	)
	args = parser.parse_args()
	return args


#============================================
def resolve_latest_fetch_input(input_path: str) -> str:
	"""
	Fallback to latest dated fetch JSONL file when default input is missing.
	"""
	if os.path.isfile(input_path):
		return input_path
	import glob
	directory = os.path.dirname(input_path)
	pattern = os.path.join(directory, "github_data_*.jsonl")
	candidates = []
	for candidate in glob.glob(pattern):
		filename = os.path.basename(candidate)
		if filename == "github_data.jsonl":
			continue
		if os.path.isfile(candidate):
			candidates.append(candidate)
	if not candidates:
		return input_path
	candidates.sort(key=os.path.getmtime, reverse=True)
	return candidates[0]


#============================================
def _sanitize_repo_slug(repo_full_name: str) -> str:
	"""
	Convert a repo full name like 'user/repo' to a safe filename slug.
	"""
	# replace slashes and other non-alphanumeric chars with underscores
	slug = re.sub(r"[^a-zA-Z0-9]", "_", repo_full_name)
	slug = slug.strip("_").lower()
	return slug


#============================================
def _changelog_summary_quality_issue(text: str) -> str:
	"""
	Return a validation issue string when changelog summary is unusable.

	Returns empty string if OK; returns issue description if
	empty or error payload.
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
def _referee_changelog(
	client,
	draft_a: str,
	draft_b: str,
	max_tokens: int,
) -> str:
	"""
	Run referee comparison between two changelog summary drafts.
	"""
	# randomize label assignment to avoid position bias
	labels = [("A", "B"), ("B", "A")]
	label_a, label_b = random.choice(labels)
	if label_a == "B":
		draft_a, draft_b = draft_b, draft_a
	template = prompt_loader.load_prompt("depth_referee_changelog.txt")
	prompt = prompt_loader.render_prompt(template, {
		"label_a": label_a,
		"label_b": label_b,
		"draft_a": draft_a,
		"draft_b": draft_b,
	})
	raw = client.generate(
		prompt=prompt,
		purpose="changelog referee",
		max_tokens=max_tokens,
	).strip()
	return raw


#============================================
def _polish_changelog(
	client,
	drafts: list,
	depth: int,
	max_tokens: int,
) -> str:
	"""
	Run polish pass to merge multiple changelog summary drafts into one.
	"""
	parts = []
	for i, draft in enumerate(drafts, start=1):
		parts.append(f"Draft {i}:\n{draft}")
	drafts_block = "\n\n".join(parts)
	template = prompt_loader.load_prompt("depth_polish_changelog.txt")
	prompt = prompt_loader.render_prompt(template, {
		"draft_count": str(len(drafts)),
		"drafts_block": drafts_block,
	})
	polished = client.generate(
		prompt=prompt,
		purpose="changelog polish",
		max_tokens=max_tokens,
	).strip()
	return polished


#============================================
def summarize_jsonl_changelogs(
	input_path: str,
	client,
	threshold: int,
	log_fn=None,
	chunk_size: int = 2250,
	chunk_overlap: int = 250,
	depth: int = 1,
	cache_dir: str = "",
	continue_mode: bool = True,
	max_tokens: int = 1024,
) -> int:
	"""
	Read JSONL, summarize long repo_changelog entries, write back atomically.

	For each repo_changelog record where latest_entry exceeds threshold,
	the entry is summarized via changelog_summarizer.summarize_long_changelog().
	At depth 2+, multiple drafts are generated and refined via the depth
	pipeline. All other records pass through unchanged. The file is rewritten
	atomically via a temp file and rename.

	Args:
		input_path: path to the JSONL file.
		client: local-llm-wrapper LLMClient instance.
		threshold: character count above which summarization triggers.
		log_fn: optional callable for progress logging.
		chunk_size: characters per chunk for splitting long entries.
		chunk_overlap: overlap between consecutive chunks.
		depth: LLM generation depth (1-4).
		cache_dir: directory for depth pipeline cache files.
		continue_mode: whether to load cached drafts in depth mode.
		max_tokens: max generation tokens per LLM call.

	Returns:
		Count of entries that were summarized.
	"""
	# read all lines from the JSONL
	with open(input_path, "r", encoding="utf-8") as handle:
		raw_lines = handle.readlines()

	summarized_count = 0
	output_lines = []
	for raw_line in raw_lines:
		stripped = raw_line.strip()
		if not stripped:
			output_lines.append(raw_line)
			continue
		record = json.loads(stripped)
		# only process repo_changelog records with long latest_entry
		if record.get("record_type") == "repo_changelog":
			entry_text = record.get("latest_entry", "")
			if len(entry_text) > threshold:
				repo_name = record.get("repo_full_name", "unknown")
				if log_fn:
					log_fn(
						f"Summarizing changelog for {repo_name} "
						f"({len(entry_text)} chars)"
					)
				summary = _summarize_one_entry(
					client, entry_text, threshold, chunk_size,
					chunk_overlap, max_tokens, log_fn,
					depth, cache_dir, continue_mode, repo_name,
				)
				record["latest_entry"] = summary
				summarized_count += 1
		# write record back as compact JSON line
		output_lines.append(json.dumps(record, ensure_ascii=True) + "\n")

	# atomic write: temp file in same directory, then rename
	dir_name = os.path.dirname(os.path.abspath(input_path))
	fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".jsonl.tmp")
	os.close(fd)
	with open(tmp_path, "w", encoding="utf-8") as handle:
		handle.writelines(output_lines)
	os.replace(tmp_path, input_path)
	return summarized_count


#============================================
def _summarize_one_entry(
	client,
	entry_text: str,
	threshold: int,
	chunk_size: int,
	chunk_overlap: int,
	max_tokens: int,
	log_fn,
	depth: int,
	cache_dir: str,
	continue_mode: bool,
	repo_name: str,
) -> str:
	"""
	Summarize a single long changelog entry, using depth pipeline if depth >= 2.
	"""
	if depth <= 1:
		# single-pass: call summarize_long_changelog once
		summary = changelog_summarizer.summarize_long_changelog(
			client, entry_text, threshold=threshold,
			chunk_size=chunk_size, overlap=chunk_overlap,
			max_tokens=max_tokens, log_fn=log_fn,
		)
		return summary

	# depth 2+: use depth pipeline for multi-draft generation
	repo_slug = _sanitize_repo_slug(repo_name)

	def _gen_draft() -> str:
		return changelog_summarizer.summarize_long_changelog(
			client, entry_text, threshold=threshold,
			chunk_size=chunk_size, overlap=chunk_overlap,
			max_tokens=max_tokens, log_fn=log_fn,
		)

	def _referee(draft_a: str, draft_b: str) -> str:
		return _referee_changelog(client, draft_a, draft_b, max_tokens)

	def _polish(drafts: list, d: int) -> str:
		return _polish_changelog(client, drafts, d, max_tokens)

	result = depth_orchestrator.run_depth_pipeline(
		generate_draft_fn=_gen_draft,
		referee_fn=_referee,
		polish_fn=_polish,
		depth=depth,
		cache_dir=cache_dir,
		cache_key_prefix=f"changelog_{repo_slug}",
		continue_mode=continue_mode,
		max_tokens=max_tokens,
		quality_check_fn=_changelog_summary_quality_issue,
		logger=log_fn,
	)
	return result


#============================================
def main() -> None:
	"""
	Run changelog summarization on fetch JSONL.
	"""
	args = parse_args()
	settings, settings_path = pipeline_settings.load_settings(args.settings)
	user = pipeline_settings.get_github_username(settings, "vosslab")
	# resolve input path with user scoping
	input_path = pipeline_settings.resolve_user_scoped_out_path(
		args.input_file,
		DEFAULT_INPUT_PATH,
		user,
	)
	if input_path == pipeline_settings.resolve_user_scoped_out_path(
		DEFAULT_INPUT_PATH,
		DEFAULT_INPUT_PATH,
		user,
	):
		input_path = resolve_latest_fetch_input(input_path)
	log_step(f"Using settings file: {settings_path}")
	log_step(f"Input JSONL: {os.path.abspath(input_path)}")
	log_step(f"Threshold: {args.threshold} chars")

	if not os.path.isfile(input_path):
		raise FileNotFoundError(f"Missing JSONL input: {input_path}")

	# resolve LLM transport and model from settings + CLI overrides
	default_transport = pipeline_settings.get_enabled_llm_transport(settings)
	default_model = pipeline_settings.get_llm_provider_model(settings, default_transport)
	transport_name = args.llm_transport or default_transport
	model_override = default_model
	if args.llm_model is not None:
		model_override = args.llm_model.strip()

	# resolve depth from settings + CLI override
	default_depth = pipeline_settings.get_llm_depth(settings, 1)
	depth = default_depth if args.depth is None else args.depth
	depth_orchestrator.validate_depth(depth)

	# resolve max_tokens from settings + CLI override
	default_max_tokens = pipeline_settings.get_setting_int(
		settings, ["llm", "max_tokens"], 1200,
	)
	max_tokens = default_max_tokens if args.llm_max_tokens is None else args.llm_max_tokens

	# build cache directory for depth pipeline
	cache_dir = os.path.join(
		os.path.dirname(os.path.abspath(input_path)), "depth_cache",
	)

	log_step(f"Depth: {depth}, continue_mode: {args.continue_mode}")

	# create LLM client lazily only if needed
	client = outline_llm.create_llm_client(
		script_file=__file__,
		transport_name=transport_name,
		model_override=model_override,
		quiet=True,
	)
	count = summarize_jsonl_changelogs(
		input_path, client, args.threshold, log_fn=log_step,
		chunk_size=args.chunk_size, chunk_overlap=args.chunk_overlap,
		depth=depth, cache_dir=cache_dir,
		continue_mode=args.continue_mode, max_tokens=max_tokens,
	)
	log_step(f"Summarized {count} changelog entry(ies).")
	log_step("Changelog summarization stage complete.")


if __name__ == "__main__":
	main()
