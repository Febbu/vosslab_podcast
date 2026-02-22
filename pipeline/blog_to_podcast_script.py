#!/usr/bin/env python3
import argparse
import glob
import json
import os
import random
import re
from datetime import datetime

from podlib import depth_orchestrator
from podlib import outline_llm
from podlib import pipeline_settings
from podlib import pipeline_text_utils

from podlib import prompt_loader


WHITESPACE_RE = re.compile(r"\s+")
SPEAKER_LINE_RE = re.compile(r"^\s*([A-Za-z0-9_ -]+)\s*:\s*(.+?)\s*$")
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
H1_RE = re.compile(r"^#\s+(.+)", re.MULTILINE)
DATE_STAMP_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
DEFAULT_INPUT_PATH = "out/blog_post.md"
DEFAULT_OUTPUT_PATH = "out/podcast_script.txt"
DEFAULT_NARRATION_OUTPUT_PATH = "out/podcast_narration.txt"

# Q101 radio personality labels in speaker order
ALL_SPEAKER_LABELS = ["BHOST", "KCOLOR", "CPRODUCER"]
# mapping for files in pipeline/prompts/
SPEAKER_PROMPT_FILES = ["bhost.txt", "kcolor.txt", "cproducer.txt"]


#============================================
def log_step(message: str) -> None:
	"""
	Print one timestamped progress line.
	"""
	now_text = datetime.now().strftime("%H:%M:%S")
	print(f"[blog_to_podcast_script {now_text}] {message}", flush=True)


#============================================
def parse_args() -> argparse.Namespace:
	"""
	Parse command-line arguments.
	"""
	parser = argparse.ArgumentParser(
		description="Render a target-length N-speaker podcast script from a blog Markdown file."
	)
	parser.add_argument(
		"--input",
		default=DEFAULT_INPUT_PATH,
		help="Path to blog Markdown input file.",
	)
	parser.add_argument(
		"--output",
		default=DEFAULT_OUTPUT_PATH,
		help="Path to output podcast script text file.",
	)
	parser.add_argument(
		"--num-speakers",
		type=int,
		default=3,
		help="Number of speakers to include in the script (1-3).",
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
		'-d', '--depth', dest='depth', type=int, default=None,
		help="LLM generation depth 1-4 (higher = more candidates, better quality).",
	)
	parser.add_argument(
		'--skip-narration',
		dest="skip_narration",
		action="store_true",
		help="Skip generating 1-speaker narration output.",
	)
	parser.set_defaults(skip_narration=False)
	args = parser.parse_args()
	return args


#============================================
def load_blog_markdown(path: str) -> str:
	"""
	Load blog Markdown text from disk.
	"""
	if not os.path.isfile(path):
		raise FileNotFoundError(f"Missing blog input: {path}")
	with open(path, "r", encoding="utf-8") as handle:
		text = handle.read()
	return text.strip()


#============================================
def resolve_latest_blog_input(input_path: str) -> str:
	"""
	Fallback to latest dated blog Markdown file when default input is missing.
	"""
	if os.path.isfile(input_path):
		return input_path
	directory = os.path.dirname(input_path) or "."
	pattern = os.path.join(directory, "blog_post_*.md")
	candidates = []
	for candidate in glob.glob(pattern):
		if os.path.isfile(candidate):
			candidates.append(candidate)
	if not candidates:
		return input_path
	candidates.sort(key=os.path.getmtime, reverse=True)
	return candidates[0]


#============================================
def local_date_stamp() -> str:
	"""
	Return local-date stamp for filenames.
	"""
	return datetime.now().astimezone().strftime("%Y-%m-%d")


#============================================
def date_stamp_output_path(output_path: str, date_text: str, default_path: str) -> str:
	"""
	Ensure output filename includes one local-date stamp.
	"""
	candidate = (output_path or "").strip() or default_path
	candidate = candidate.replace("{date}", date_text)
	directory, filename = os.path.split(candidate)
	if not filename:
		filename = os.path.basename(default_path)
	stem, extension = os.path.splitext(filename)
	if not extension:
		extension = ".txt"
	if DATE_STAMP_RE.search(filename):
		dated_filename = filename
	else:
		dated_filename = f"{stem}-{date_text}{extension}"
	return os.path.join(directory, dated_filename)


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
	Build Q101 radio personality speaker labels.
	"""
	if num_speakers < 1:
		raise RuntimeError("num-speakers must be at least 1.")
	if num_speakers > len(ALL_SPEAKER_LABELS):
		raise RuntimeError(f"num-speakers must be at most {len(ALL_SPEAKER_LABELS)}.")
	return list(ALL_SPEAKER_LABELS[:num_speakers])


#============================================
def load_speaker_styles(num_speakers: int) -> str:
	"""
	Load speaker personality descriptions from prompts/ folder.
	"""
	speaker_files = SPEAKER_PROMPT_FILES[:num_speakers]
	parts = [prompt_loader.load_prompt("show_intro.txt")]
	for filename in speaker_files:
		parts.append(prompt_loader.load_prompt(filename))
	return "\n\n".join(parts)


#============================================
def build_podcast_lines(blog_text: str, speaker_labels: list[str]) -> list[tuple[str, str]]:
	"""
	Build ordered deterministic fallback speaker lines from blog markdown.
	"""
	# extract H1 title
	title_match = H1_RE.search(blog_text)
	title = title_match.group(1).strip() if title_match else "Daily engineering update"
	# gather first few paragraph lines
	paragraphs = []
	for line in blog_text.splitlines():
		stripped = line.strip()
		if not stripped or stripped.startswith("#"):
			continue
		paragraphs.append(stripped)
		if len(paragraphs) >= 6:
			break

	lines: list[tuple[str, str]] = []
	lines.append(
		(speaker_labels[0], f"Welcome to the daily engineering report. Today: {title}.")
	)
	# distribute paragraph sentences across speakers
	for index, para in enumerate(paragraphs):
		label = speaker_labels[index % len(speaker_labels)]
		lines.append((label, para))
	lines.append(
		(speaker_labels[0], "That wraps up today's daily engineering report.")
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
	Normalize a speaker token to uppercase with underscores.
	"""
	normalized = re.sub(r"[^A-Za-z0-9]+", "_", (token or "").strip().upper()).strip("_")
	# handle legacy SPEAKER_N format
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
def build_speaker_format_text(speaker_labels: list[str]) -> str:
	"""
	Build speaker format instruction text from label list.
	"""
	lines = []
	for label in speaker_labels:
		lines.append(f"{label}: spoken text")
	return "\n".join(lines)


#============================================
def build_podcast_script_prompt(
	blog_text: str,
	speaker_labels: list[str],
	word_limit: int,
) -> str:
	"""
	Build multi-speaker podcast script prompt from blog text.
	"""
	num_speakers = len(speaker_labels)
	speaker_styles = load_speaker_styles(num_speakers)
	speaker_format = build_speaker_format_text(speaker_labels)
	template = prompt_loader.load_prompt("podcast_script.txt")
	prompt = prompt_loader.render_prompt_with_target(template, {
		"num_speakers": str(num_speakers),
		"word_limit": str(word_limit),
		"speaker_styles": speaker_styles,
		"speaker_format": speaker_format,
		"blog_text": blog_text,
	}, target_value=str(word_limit), unit="words", document_name="podcast script")
	return prompt


#============================================
def build_podcast_narration_prompt(
	blog_text: str,
	word_limit: int,
) -> str:
	"""
	Build 1-speaker narration prompt from blog text.
	"""
	speaker_styles = load_speaker_styles(1)
	template = prompt_loader.load_prompt("podcast_narration.txt")
	prompt = prompt_loader.render_prompt_with_target(template, {
		"word_limit": str(word_limit),
		"speaker_styles": speaker_styles,
		"blog_text": blog_text,
	}, target_value=str(word_limit), unit="words", document_name="podcast narration")
	return prompt


#============================================
def build_podcast_trim_prompt(
	draft_text: str,
	speaker_labels: list[str],
	word_limit: int,
) -> str:
	"""
	Build trim prompt for podcast script revision.
	"""
	speaker_format = build_speaker_format_text(speaker_labels)
	context = {
		"speaker_labels": speaker_labels,
		"draft_text": draft_text,
		"draft_word_count": pipeline_text_utils.count_words(draft_text),
	}
	context_json = json.dumps(context, ensure_ascii=True, indent=2)
	template = prompt_loader.load_prompt("podcast_trim.txt")
	prompt = prompt_loader.render_prompt_with_target(template, {
		"word_limit": str(word_limit),
		"speaker_format": speaker_format,
		"context_json": context_json,
	}, target_value=str(word_limit), unit="words", document_name="podcast script")
	return prompt


#============================================
def _referee_podcast(
	client,
	draft_a: str,
	draft_b: str,
	max_tokens: int,
) -> str:
	"""
	Run referee comparison between two podcast script draft texts.
	"""
	# randomize label order to avoid positional bias
	labels = [("A", "B"), ("B", "A")]
	label_a, label_b = random.choice(labels)
	if label_a == "B":
		draft_a, draft_b = draft_b, draft_a
	template = prompt_loader.load_prompt("depth_referee_podcast.txt")
	prompt = prompt_loader.render_prompt(template, {
		"label_a": label_a,
		"label_b": label_b,
		"draft_a": draft_a,
		"draft_b": draft_b,
	})
	raw = client.generate(
		prompt=prompt,
		purpose="podcast referee",
		max_tokens=max_tokens,
	).strip()
	return raw


#============================================
def _polish_podcast(
	client,
	drafts: list,
	depth: int,
	word_limit: int,
	max_tokens: int,
) -> str:
	"""
	Run polish pass to merge multiple podcast script drafts into one final script.
	"""
	parts = []
	for i, draft in enumerate(drafts, start=1):
		parts.append(f"Draft {i}:\n{draft}")
	drafts_block = "\n\n".join(parts)
	template = prompt_loader.load_prompt("depth_polish_podcast.txt")
	prompt = prompt_loader.render_prompt(template, {
		"draft_count": str(len(drafts)),
		"drafts_block": drafts_block,
		"target_value": str(word_limit),
		"target_unit": "words",
	})
	polished = client.generate(
		prompt=prompt,
		purpose="podcast polish",
		max_tokens=max_tokens,
	).strip()
	polished = outline_llm.strip_xml_wrapper(polished)
	return polished


#============================================
def generate_podcast_lines_with_llm(
	blog_text: str,
	speaker_labels: list[str],
	transport_name: str,
	model_override: str,
	max_tokens: int,
	word_limit: int,
	depth: int = 1,
	cache_dir: str = "",
	continue_mode: bool = True,
	logger=None,
) -> list[tuple[str, str]]:
	"""
	Generate podcast lines with single-pass or depth-pipeline blog summarization.
	"""
	client = create_llm_client(transport_name, model_override, quiet=False)
	prompt = build_podcast_script_prompt(blog_text, speaker_labels, word_limit)

	def _generate_one_draft_text() -> str:
		"""Generate a single podcast script as raw text."""
		raw_text = client.generate(
			prompt=prompt,
			purpose="podcast blog script",
			max_tokens=max_tokens,
		).strip()
		raw_text = outline_llm.strip_xml_wrapper(raw_text)
		issue = podcast_quality_issue(raw_text)
		if issue:
			retry_prompt = (
				"Regenerate the podcast script as clean speaker lines.\n"
				+ f"Target around {word_limit} words.\n"
				+ "Please do better.\n"
				+ "Format each line as LABEL: text.\n\n"
				+ prompt
			)
			raw_text = client.generate(
				prompt=retry_prompt,
				purpose="podcast blog script retry",
				max_tokens=max_tokens,
			).strip()
			raw_text = outline_llm.strip_xml_wrapper(raw_text)
		return raw_text

	# depth 1: original behavior
	if depth <= 1:
		if logger:
			logger(f"Generating {len(speaker_labels)}-speaker podcast script (target={word_limit} words).")
		raw_text = _generate_one_draft_text()
		lines = parse_generated_script_lines(raw_text, speaker_labels)
		lines = ensure_required_speakers(lines, speaker_labels)
		return trim_lines_to_word_limit(lines, word_limit)

	# depth 2-4: use depth pipeline on text, then parse at the end
	if logger:
		logger(
			f"Generating {len(speaker_labels)}-speaker podcast script "
			+ f"with depth={depth} (target={word_limit} words)."
		)

	def _referee(draft_a: str, draft_b: str) -> str:
		return _referee_podcast(client, draft_a, draft_b, max_tokens)

	def _polish(drafts: list, d: int) -> str:
		return _polish_podcast(client, drafts, d, word_limit, max_tokens)

	final_text = depth_orchestrator.run_depth_pipeline(
		generate_draft_fn=_generate_one_draft_text,
		referee_fn=_referee,
		polish_fn=_polish,
		depth=depth,
		cache_dir=cache_dir,
		cache_key_prefix="podcast",
		continue_mode=continue_mode,
		max_tokens=max_tokens,
		quality_check_fn=podcast_quality_issue,
		logger=logger,
	)
	# reparse the final text into speaker lines
	lines = parse_generated_script_lines(final_text, speaker_labels)
	lines = ensure_required_speakers(lines, speaker_labels)
	return trim_lines_to_word_limit(lines, word_limit)


#============================================
def generate_narration_lines_with_llm(
	blog_text: str,
	transport_name: str,
	model_override: str,
	max_tokens: int,
	word_limit: int,
	logger=None,
) -> list[tuple[str, str]]:
	"""
	Generate 1-speaker narration lines from blog text.
	"""
	client = create_llm_client(transport_name, model_override, quiet=False)
	prompt = build_podcast_narration_prompt(blog_text, word_limit)
	if logger:
		logger(f"Generating 1-speaker narration (target={word_limit} words).")
	raw_text = client.generate(
		prompt=prompt,
		purpose="podcast blog narration",
		max_tokens=max_tokens,
	).strip()
	raw_text = outline_llm.strip_xml_wrapper(raw_text)
	issue = podcast_quality_issue(raw_text)
	if issue:
		if logger:
			logger(f"Narration draft flagged ({issue}); retrying once.")
		retry_prompt = (
			"Regenerate the narration as clean BHOST: lines.\n"
			+ f"Target around {word_limit} words.\n"
			+ "Please do better.\n\n"
			+ prompt
		)
		raw_text = client.generate(
			prompt=retry_prompt,
			purpose="podcast blog narration retry",
			max_tokens=max_tokens,
		).strip()
		raw_text = outline_llm.strip_xml_wrapper(raw_text)
	narration_labels = ["BHOST"]
	lines = parse_generated_script_lines(raw_text, narration_labels)
	lines = ensure_required_speakers(lines, narration_labels)
	return trim_lines_to_word_limit(lines, word_limit)


#============================================
def main() -> None:
	"""
	Generate podcast script and narration from blog Markdown with LLM.
	"""
	args = parse_args()
	settings, settings_path = pipeline_settings.load_settings(args.settings)
	user = pipeline_settings.get_github_username(settings, "vosslab")
	default_transport = pipeline_settings.get_enabled_llm_transport(settings)
	default_model = pipeline_settings.get_llm_provider_model(settings, default_transport)
	default_max_tokens = pipeline_settings.get_setting_int(
		settings, ["llm", "max_tokens"], 1200,
	)
	default_depth = pipeline_settings.get_llm_depth(settings, 1)
	input_path = pipeline_settings.resolve_user_scoped_out_path(
		args.input,
		DEFAULT_INPUT_PATH,
		user,
	)
	# auto-discover latest blog markdown if default path is missing
	input_path = resolve_latest_blog_input(input_path)
	output_path_arg = pipeline_settings.resolve_user_scoped_out_path(
		args.output,
		DEFAULT_OUTPUT_PATH,
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
	# depth: CLI overrides settings.yaml
	depth = args.depth if args.depth is not None else default_depth
	depth_orchestrator.validate_depth(depth)

	log_step(
		"Starting podcast script stage with "
		+ f"input={os.path.abspath(input_path)}, output={os.path.abspath(output_path_arg)}, "
		+ f"num_speakers={args.num_speakers}, word_limit={args.word_limit}"
	)
	log_step(f"Using settings file: {settings_path}")
	log_step(
		"Using LLM settings: "
		+ f"transport={transport_name}, model={model_override or 'auto'}, "
		+ f"max_tokens={max_tokens}, depth={depth}"
	)
	log_step(
		"LLM execution path for this run: "
		+ describe_llm_execution_path(transport_name, model_override)
	)
	log_step("Loading blog Markdown.")
	blog_text = load_blog_markdown(input_path)
	if not blog_text:
		log_step("Blog input is empty; exiting podcast script stage without LLM calls.")
		log_step("No podcast script file written.")
		return
	log_step(f"Blog text loaded ({len(blog_text)} chars).")
	log_step("Building speaker label set.")
	speaker_labels = build_speaker_labels(args.num_speakers)
	log_step(f"Speaker labels: {speaker_labels}")

	date_text = local_date_stamp()
	# build depth cache directory alongside the output
	depth_cache_dir = os.path.join(
		os.path.dirname(os.path.abspath(output_path_arg)), "depth_cache",
	)

	# --- Multi-speaker script ---
	log_step("Generating multi-speaker podcast script from blog.")
	try:
		lines = generate_podcast_lines_with_llm(
			blog_text,
			speaker_labels=speaker_labels,
			transport_name=transport_name,
			model_override=model_override,
			max_tokens=max_tokens,
			word_limit=args.word_limit,
			depth=depth,
			cache_dir=depth_cache_dir,
			continue_mode=True,
			logger=log_step,
		)
	except RuntimeError as error:
		log_step(f"LLM generation failed ({error}); using deterministic fallback script.")
		lines = build_podcast_lines(blog_text, speaker_labels)

	lines = ensure_required_speakers(lines, speaker_labels)
	trimmed_lines = trim_lines_to_word_limit(lines, args.word_limit)
	spoken_word_count = count_script_words(trimmed_lines)
	used_speakers = {speaker for speaker, _text in trimmed_lines}
	if len(used_speakers) < len(speaker_labels):
		log_step("Speaker coverage dropped after trim; restoring missing speakers.")
		trimmed_lines = ensure_required_speakers(trimmed_lines, speaker_labels)
		trimmed_lines = trim_lines_to_word_limit(trimmed_lines, args.word_limit)
		spoken_word_count = count_script_words(trimmed_lines)

	dated_output = date_stamp_output_path(output_path_arg, date_text, DEFAULT_OUTPUT_PATH)
	output_path = os.path.abspath(dated_output)
	output_dir = os.path.dirname(output_path)
	if output_dir:
		os.makedirs(output_dir, exist_ok=True)
	script_text = render_script_text(trimmed_lines)
	log_step(f"Writing podcast script output to {output_path}")
	with open(output_path, "w", encoding="utf-8") as handle:
		handle.write(script_text)
	log_step(
		f"Wrote {output_path} "
		+ f"({spoken_word_count} words, {args.num_speakers} speakers; target={args.word_limit})"
	)

	# --- 1-speaker narration ---
	if args.skip_narration:
		log_step("Skipping 1-speaker narration by request.")
		return
	log_step("Generating 1-speaker narration from blog.")
	narration_output_arg = pipeline_settings.resolve_user_scoped_out_path(
		DEFAULT_NARRATION_OUTPUT_PATH,
		DEFAULT_NARRATION_OUTPUT_PATH,
		user,
	)
	try:
		narration_lines = generate_narration_lines_with_llm(
			blog_text,
			transport_name=transport_name,
			model_override=model_override,
			max_tokens=max_tokens,
			word_limit=args.word_limit,
			logger=log_step,
		)
	except RuntimeError as error:
		log_step(f"Narration LLM failed ({error}); using fallback.")
		narration_lines = build_podcast_lines(blog_text, ["BHOST"])

	narration_lines = ensure_required_speakers(narration_lines, ["BHOST"])
	narration_lines = trim_lines_to_word_limit(narration_lines, args.word_limit)
	narration_words = count_script_words(narration_lines)
	narration_dated = date_stamp_output_path(
		narration_output_arg, date_text, DEFAULT_NARRATION_OUTPUT_PATH,
	)
	narration_path = os.path.abspath(narration_dated)
	narration_dir = os.path.dirname(narration_path)
	if narration_dir:
		os.makedirs(narration_dir, exist_ok=True)
	narration_text = render_script_text(narration_lines)
	log_step(f"Writing narration output to {narration_path}")
	with open(narration_path, "w", encoding="utf-8") as handle:
		handle.write(narration_text)
	log_step(
		f"Wrote {narration_path} ({narration_words} words, 1 speaker; target={args.word_limit})"
	)


if __name__ == "__main__":
	main()
