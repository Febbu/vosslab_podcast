#!/usr/bin/env python3
"""Summarize long changelog entries in fetch JSONL via LLM.

Reads the fetch-stage JSONL, finds repo_changelog records with long
latest_entry fields, summarizes them using changelog_summarizer, and
writes the updated JSONL back in place. Short entries and non-changelog
records pass through unchanged.
"""

import argparse
import json
import os
import tempfile
from datetime import datetime

from podlib import outline_llm
from podlib import pipeline_settings

import changelog_summarizer


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
def summarize_jsonl_changelogs(
	input_path: str,
	client,
	threshold: int,
	log_fn=None,
) -> int:
	"""
	Read JSONL, summarize long repo_changelog entries, write back atomically.

	For each repo_changelog record where latest_entry exceeds threshold,
	the entry is summarized via changelog_summarizer.summarize_long_changelog().
	All other records pass through unchanged. The file is rewritten atomically
	via a temp file and rename.

	Args:
		input_path: path to the JSONL file.
		client: local-llm-wrapper LLMClient instance.
		threshold: character count above which summarization triggers.
		log_fn: optional callable for progress logging.

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
				summary = changelog_summarizer.summarize_long_changelog(
					client, entry_text, threshold=threshold, log_fn=log_fn,
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

	# create LLM client lazily only if needed
	client = outline_llm.create_llm_client(
		script_file=__file__,
		transport_name=transport_name,
		model_override=model_override,
		quiet=True,
	)
	count = summarize_jsonl_changelogs(
		input_path, client, args.threshold, log_fn=log_step,
	)
	log_step(f"Summarized {count} changelog entry(ies).")
	log_step("Changelog summarization stage complete.")


if __name__ == "__main__":
	main()
