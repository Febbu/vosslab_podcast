"""Depth orchestration for multi-draft LLM pipelines.

Controls how many drafts are generated, whether referee and polish
passes run, and manages draft caching for continue-mode resumption.
"""

# Standard Library
import os
import re


#============================================
def validate_depth(depth: int) -> None:
	"""Raise ValueError if depth is not in the valid range 1-4.

	Args:
		depth: Draft depth level to validate.
	"""
	if depth not in (1, 2, 3, 4):
		raise ValueError(f"depth must be 1, 2, 3, or 4; got {depth}")


#============================================
def compute_draft_count(depth: int) -> int:
	"""Return the number of drafts to generate for a given depth.

	Args:
		depth: Draft depth level (1-4).

	Returns:
		Number of drafts equal to the depth value.
	"""
	validate_depth(depth)
	return depth


#============================================
def needs_referee(depth: int) -> bool:
	"""Return True only when depth requires a referee tournament.

	Args:
		depth: Draft depth level (1-4).

	Returns:
		True for depth 4, False otherwise.
	"""
	validate_depth(depth)
	return depth == 4


#============================================
def needs_polish(depth: int) -> bool:
	"""Return True when depth requires a polish pass.

	Args:
		depth: Draft depth level (1-4).

	Returns:
		True for depth 2-4, False for depth 1.
	"""
	validate_depth(depth)
	return depth >= 2


#============================================
def build_referee_brackets(drafts: list) -> list:
	"""Pair adjacent drafts for tournament-style referee comparison.

	Args:
		drafts: List of draft strings to pair up.

	Returns:
		List of (draft_a, draft_b) tuples pairing adjacent items.
		For 4 items: [(draft[0], draft[1]), (draft[2], draft[3])].
		For 2 items: [(draft[0], draft[1])].
	"""
	brackets = []
	# step through drafts in pairs of two
	for i in range(0, len(drafts) - 1, 2):
		pair = (drafts[i], drafts[i + 1])
		brackets.append(pair)
	return brackets


#============================================
def parse_referee_winner(raw: str, label_a: str, label_b: str) -> str:
	"""Extract the winner label from referee LLM output.

	Looks for a <winner>...</winner> tag in raw text and matches
	the content against label_a or label_b (case-insensitive).

	Args:
		raw: Raw referee output containing a <winner> tag.
		label_a: Label for the first draft.
		label_b: Label for the second draft.

	Returns:
		The matching label string. On parse failure, returns label_b
		to avoid silent A-bias.
	"""
	# search for <winner>...</winner> tag
	match = re.search(r"<winner>\s*(.*?)\s*</winner>", raw, re.IGNORECASE)
	if match is None:
		print(f"WARNING: no <winner> tag found in referee output; defaulting to {label_b}")
		return label_b
	content = match.group(1).strip().lower()
	# compare against both labels case-insensitively
	if content == label_a.strip().lower():
		return label_a
	if content == label_b.strip().lower():
		return label_b
	# content did not match either label
	print(
		f"WARNING: <winner> content '{match.group(1).strip()}' "
		f"does not match '{label_a}' or '{label_b}'; defaulting to {label_b}"
	)
	return label_b


#============================================
def _cache_path(cache_dir: str, cache_key_prefix: str, depth: int, index: int) -> str:
	"""Build the file path for a cached draft.

	Args:
		cache_dir: Directory for cache files.
		cache_key_prefix: Prefix for the cache filename.
		depth: Current depth level.
		index: Zero-based draft index.

	Returns:
		Full file path for the cache file.
	"""
	filename = f"{cache_key_prefix}_d{depth}_i{index}.txt"
	path = os.path.join(cache_dir, filename)
	return path


#============================================
def _load_cached_draft(path: str) -> str:
	"""Load a cached draft from disk if it exists.

	Args:
		path: File path to read.

	Returns:
		Draft text, or empty string if file does not exist.
	"""
	if not os.path.isfile(path):
		return ""
	with open(path, "r") as f:
		text = f.read()
	return text


#============================================
def _save_draft_cache(path: str, text: str) -> None:
	"""Write a draft to a cache file, creating directories as needed.

	Args:
		path: File path to write.
		text: Draft text to save.
	"""
	# ensure parent directory exists
	parent = os.path.dirname(path)
	if parent:
		os.makedirs(parent, exist_ok=True)
	with open(path, "w") as f:
		f.write(text)


#============================================
def _log(logger, msg: str) -> None:
	"""Call the logger if it is not None.

	Args:
		logger: Callable(str) or None.
		msg: Message to log.
	"""
	if logger is not None:
		logger(msg)


#============================================
def run_depth_pipeline(
	generate_draft_fn,
	referee_fn,
	polish_fn,
	depth: int,
	cache_dir: str,
	cache_key_prefix: str,
	continue_mode: bool,
	max_tokens: int,
	quality_check_fn,
	logger=None,
) -> str:
	"""Run the full depth-based draft generation pipeline.

	Generates one or more drafts, optionally runs referee brackets
	and a polish pass, and returns the best result.

	Args:
		generate_draft_fn: Callable() -> str that generates one draft.
		referee_fn: Callable(draft_a, draft_b) -> str returning raw
			referee output with <winner> tag. Can be None when not needed.
		polish_fn: Callable(drafts, depth) -> str returning polished
			output. Can be None when not needed.
		depth: Draft depth level 1-4.
		cache_dir: Directory for draft cache files.
		cache_key_prefix: Prefix for cache filenames.
		continue_mode: Whether to load cached drafts.
		max_tokens: Token limit (passed through, not used directly).
		quality_check_fn: Callable(text) -> str returning empty string
			if OK, or an issue description if quality is bad.
		logger: Callable(msg) -> None for progress messages, or None.

	Returns:
		Final output string (polished or best draft).
	"""
	validate_depth(depth)
	draft_count = compute_draft_count(depth)

	# -- generate drafts --
	drafts = []
	for i in range(draft_count):
		cache_file = _cache_path(cache_dir, cache_key_prefix, depth, i)
		# try loading from cache in continue mode
		if continue_mode:
			cached = _load_cached_draft(cache_file)
			if cached:
				_log(logger, f"Loaded cached draft {i + 1}/{draft_count}")
				drafts.append(cached)
				continue
		# generate a new draft
		_log(logger, f"Generating draft {i + 1}/{draft_count}")
		draft = generate_draft_fn()
		# save to cache
		_save_draft_cache(cache_file, draft)
		drafts.append(draft)

	# -- depth 1: return single draft directly --
	if depth == 1:
		return drafts[0]

	# -- depth 4: referee tournament --
	best_unpolished = drafts[0]
	if needs_referee(depth):
		_log(logger, "Running referee brackets")
		brackets = build_referee_brackets(drafts)
		winners = []
		for bracket_idx, (draft_a, draft_b) in enumerate(brackets):
			label_a = f"Draft {bracket_idx * 2 + 1}"
			label_b = f"Draft {bracket_idx * 2 + 2}"
			raw_result = referee_fn(draft_a, draft_b)
			winner_label = parse_referee_winner(raw_result, label_a, label_b)
			# pick the actual draft text based on the winning label
			if winner_label == label_a:
				winners.append(draft_a)
			else:
				winners.append(draft_b)
		# use referee winners for polish input
		drafts_for_polish = winners
		# best unpolished is the first referee winner
		best_unpolished = winners[0]
	else:
		# depth 2-3: all drafts go to polish
		drafts_for_polish = drafts

	# -- polish pass --
	_log(logger, "Running polish pass")
	polished = polish_fn(drafts_for_polish, depth)

	# -- quality check --
	issue = quality_check_fn(polished)
	if issue:
		_log(logger, f"Quality check failed: {issue}; falling back to best unpolished draft")
		return best_unpolished

	return polished
