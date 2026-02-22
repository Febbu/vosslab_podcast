#!/usr/bin/env python3
import argparse
import glob
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
XML_TAG_RE = re.compile(r"</?[a-zA-Z][a-zA-Z0-9_]*[^>]*>")
DATE_STAMP_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
H1_RE = re.compile(r"^#\s+(.+)", re.MULTILINE)
DEFAULT_INPUT_PATH = "out/blog_post.md"
DEFAULT_OUTPUT_PATH = "out/bluesky_post.txt"


#============================================
def log_step(message: str) -> None:
	"""
	Print one timestamped progress line.
	"""
	now_text = datetime.now().strftime("%H:%M:%S")
	print(f"[blog_to_bluesky_post {now_text}] {message}", flush=True)


#============================================
def parse_args() -> argparse.Namespace:
	"""
	Parse command-line arguments.
	"""
	parser = argparse.ArgumentParser(
		description="Render a target-length Bluesky post from a blog Markdown file."
	)
	parser.add_argument(
		"--input",
		default=DEFAULT_INPUT_PATH,
		help="Path to blog Markdown input file.",
	)
	parser.add_argument(
		"--output",
		default=DEFAULT_OUTPUT_PATH,
		help="Path to output text file.",
	)
	parser.add_argument(
		"--char-limit",
		type=int,
		default=280,
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
		'-d', '--depth', dest='depth', type=int, default=None,
		help="LLM generation depth 1-4 (higher = more candidates, better quality).",
	)
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
	# return the most recently modified blog file
	candidates.sort(key=os.path.getmtime, reverse=True)
	return candidates[0]


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
def strip_all_xml_tags(text: str) -> str:
	"""
	Remove all XML-like tags from text.
	"""
	return XML_TAG_RE.sub("", text).strip()


#============================================
def normalize_bluesky_text(text: str) -> str:
	"""
	Normalize LLM text into one clean Bluesky-ready line.
	"""
	clean = (text or "").strip()
	if not clean:
		return ""
	# strip any XML wrapper tags first
	clean = outline_llm.strip_xml_wrapper(clean)
	# strip ALL remaining XML tags as a hardened fallback
	clean = strip_all_xml_tags(clean)
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
def build_bluesky_text_from_blog(blog_text: str) -> str:
	"""
	Build deterministic fallback Bluesky text from blog Markdown.

	Extracts the H1 title and first sentence of the blog post.
	"""
	# try to extract the H1 title
	title_match = H1_RE.search(blog_text)
	title = title_match.group(1).strip() if title_match else ""
	# find the first paragraph sentence after the title
	lines = blog_text.splitlines()
	first_sentence = ""
	for line in lines:
		stripped = line.strip()
		if not stripped:
			continue
		# skip the title line
		if stripped.startswith("#"):
			continue
		first_sentence = stripped.split(".")[0].strip()
		if first_sentence:
			first_sentence += "."
		break
	if title and first_sentence:
		return f"{title}. {first_sentence}"
	if title:
		return title
	if first_sentence:
		return first_sentence
	# last resort: first 200 chars of blog text
	return blog_text[:200].strip()


#============================================
def build_bluesky_summarize_prompt(blog_text: str, char_limit: int) -> str:
	"""
	Build single-pass prompt to summarize blog post for Bluesky.
	"""
	template = prompt_loader.load_prompt("bluesky_summarize.txt")
	prompt = prompt_loader.render_prompt_with_target(template, {
		"char_limit": str(char_limit),
		"blog_text": blog_text,
	}, target_value=str(char_limit), unit="characters", document_name="bluesky post")
	return prompt


#============================================
def build_bluesky_trim_prompt(draft_text: str, char_limit: int) -> str:
	"""
	Build trim/retry prompt for length control.
	"""
	template = prompt_loader.load_prompt("bluesky_trim.txt")
	# pack the draft as context JSON for the trim prompt
	context = {
		"draft_text": draft_text,
		"draft_char_count": len(draft_text),
	}
	import json
	context_json = json.dumps(context, ensure_ascii=True, indent=2)
	prompt = prompt_loader.render_prompt_with_target(template, {
		"char_limit": str(char_limit),
		"context_json": context_json,
	}, target_value=str(char_limit), unit="characters", document_name="bluesky post")
	return prompt


#============================================
def _referee_bluesky(
	client,
	draft_a: str,
	draft_b: str,
	max_tokens: int,
) -> str:
	"""
	Run referee comparison between two Bluesky draft candidates.
	"""
	# randomize label order to avoid positional bias
	labels = [("A", "B"), ("B", "A")]
	label_a, label_b = random.choice(labels)
	if label_a == "B":
		draft_a, draft_b = draft_b, draft_a
	template = prompt_loader.load_prompt("depth_referee_bluesky.txt")
	prompt = prompt_loader.render_prompt(template, {
		"label_a": label_a,
		"label_b": label_b,
		"draft_a": draft_a,
		"draft_b": draft_b,
	})
	raw = client.generate(
		prompt=prompt,
		purpose="bluesky referee",
		max_tokens=max_tokens,
	).strip()
	return raw


#============================================
def _polish_bluesky(
	client,
	drafts: list,
	depth: int,
	char_limit: int,
	max_tokens: int,
) -> str:
	"""
	Run polish pass to merge multiple Bluesky drafts into one final post.
	"""
	# build the drafts block for the template
	parts = []
	for i, draft in enumerate(drafts, start=1):
		parts.append(f"Draft {i}:\n{draft}")
	drafts_block = "\n\n".join(parts)
	template = prompt_loader.load_prompt("depth_polish_bluesky.txt")
	prompt = prompt_loader.render_prompt(template, {
		"draft_count": str(len(drafts)),
		"drafts_block": drafts_block,
		"target_value": str(char_limit),
		"target_unit": "characters",
	})
	polished = client.generate(
		prompt=prompt,
		purpose="bluesky polish",
		max_tokens=max_tokens,
	).strip()
	polished = normalize_bluesky_text(polished)
	return polished


#============================================
def generate_bluesky_text_with_llm(
	blog_text: str,
	transport_name: str,
	model_override: str,
	max_tokens: int,
	char_limit: int,
	depth: int = 1,
	cache_dir: str = "",
	continue_mode: bool = True,
	logger=None,
) -> str:
	"""
	Generate Bluesky text with single-pass or depth-pipeline blog summarization.
	"""
	client = create_llm_client(transport_name, model_override, quiet=False)

	# build the base summarization prompt once
	prompt = build_bluesky_summarize_prompt(blog_text, char_limit)

	def _generate_one_draft() -> str:
		"""Generate a single Bluesky draft."""
		text = client.generate(
			prompt=prompt,
			purpose="bluesky blog summarize",
			max_tokens=max_tokens,
		).strip()
		text = normalize_bluesky_text(text)
		issue = bluesky_quality_issue(text)
		if issue:
			# one retry on quality failure
			retry_prompt = (
				"Regenerate as one clean plain-text line.\n"
				+ f"Target around {char_limit} characters.\n"
				+ "No XML tags. No Markdown. No hashtags. No emojis.\n"
				+ "Please do better.\n\n"
				+ prompt
			)
			text = client.generate(
				prompt=retry_prompt,
				purpose="bluesky blog summarize retry",
				max_tokens=max_tokens,
			).strip()
			text = normalize_bluesky_text(text)
		return text

	# depth 1: original behavior, single draft
	if depth <= 1:
		if logger:
			logger(f"Generating Bluesky summary (target={char_limit} chars).")
		text = _generate_one_draft()
		if logger:
			logger(f"Bluesky summary ready ({len(text)} chars; target={char_limit}).")
		return text

	# depth 2-4: use depth pipeline
	if logger:
		logger(f"Generating Bluesky summary with depth={depth} (target={char_limit} chars).")

	def _referee(draft_a: str, draft_b: str) -> str:
		return _referee_bluesky(client, draft_a, draft_b, max_tokens)

	def _polish(drafts: list, d: int) -> str:
		return _polish_bluesky(client, drafts, d, char_limit, max_tokens)

	text = depth_orchestrator.run_depth_pipeline(
		generate_draft_fn=_generate_one_draft,
		referee_fn=_referee,
		polish_fn=_polish,
		depth=depth,
		cache_dir=cache_dir,
		cache_key_prefix="bluesky",
		continue_mode=continue_mode,
		max_tokens=max_tokens,
		quality_check_fn=bluesky_quality_issue,
		logger=logger,
	)
	if logger:
		logger(f"Bluesky depth pipeline complete ({len(text)} chars; target={char_limit}).")
	return text


#============================================
def main() -> None:
	"""
	Generate Bluesky text from blog Markdown with LLM summarization.
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
	if args.char_limit < 1:
		raise RuntimeError("char-limit must be >= 1")
	# depth: CLI overrides settings.yaml
	depth = args.depth if args.depth is not None else default_depth
	depth_orchestrator.validate_depth(depth)

	log_step(
		"Starting bluesky stage with "
		+ f"input={os.path.abspath(input_path)}, output={os.path.abspath(output_path_arg)}, "
		+ f"char_limit={args.char_limit}"
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
		log_step("Blog input is empty; exiting bluesky stage without LLM calls.")
		log_step("No Bluesky file written.")
		return
	log_step(f"Blog text loaded ({len(blog_text)} chars).")
	log_step("Generating Bluesky text from blog summary.")
	# build depth cache directory alongside the output
	depth_cache_dir = os.path.join(os.path.dirname(os.path.abspath(output_path_arg)), "depth_cache")
	try:
		text = generate_bluesky_text_with_llm(
			blog_text,
			transport_name=transport_name,
			model_override=model_override,
			max_tokens=max_tokens,
			char_limit=args.char_limit,
			depth=depth,
			cache_dir=depth_cache_dir,
			continue_mode=True,
			logger=log_step,
		)
	except RuntimeError as error:
		log_step(f"LLM generation failed ({error}); using deterministic fallback text.")
		text = build_bluesky_text_from_blog(blog_text)

	# hard trim safety net
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
