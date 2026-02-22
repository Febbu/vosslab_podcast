"""Tests for pipeline/podlib/depth_orchestrator.py."""

# Standard Library
import os
import sys

import pytest

# add pipeline directory to path for podlib imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "pipeline"))

from podlib import depth_orchestrator


#============================================
def test_validate_depth_valid():
	"""Depths 1, 2, 3, 4 pass without error."""
	for d in (1, 2, 3, 4):
		depth_orchestrator.validate_depth(d)


#============================================
def test_validate_depth_invalid():
	"""Depths 0, 5, -1 raise ValueError."""
	for d in (0, 5, -1):
		with pytest.raises(ValueError):
			depth_orchestrator.validate_depth(d)


#============================================
def test_compute_draft_count():
	"""Draft count equals depth value."""
	assert depth_orchestrator.compute_draft_count(1) == 1
	assert depth_orchestrator.compute_draft_count(2) == 2
	assert depth_orchestrator.compute_draft_count(3) == 3
	assert depth_orchestrator.compute_draft_count(4) == 4


#============================================
def test_needs_referee():
	"""Only depth 4 needs a referee."""
	assert depth_orchestrator.needs_referee(1) is False
	assert depth_orchestrator.needs_referee(2) is False
	assert depth_orchestrator.needs_referee(3) is False
	assert depth_orchestrator.needs_referee(4) is True


#============================================
def test_needs_polish():
	"""Depth 1 does not need polish; 2, 3, 4 do."""
	assert depth_orchestrator.needs_polish(1) is False
	assert depth_orchestrator.needs_polish(2) is True
	assert depth_orchestrator.needs_polish(3) is True
	assert depth_orchestrator.needs_polish(4) is True


#============================================
def test_build_referee_brackets():
	"""4 items produce 2 pairs; 2 items produce 1 pair."""
	# 4 items -> 2 pairs
	result = depth_orchestrator.build_referee_brackets(["a", "b", "c", "d"])
	assert result == [("a", "b"), ("c", "d")]
	# 2 items -> 1 pair
	result = depth_orchestrator.build_referee_brackets(["x", "y"])
	assert result == [("x", "y")]


#============================================
def test_parse_referee_winner_valid():
	"""Extracts winner from <winner>A</winner> tag."""
	raw = "Some preamble <winner>A</winner> trailing text"
	result = depth_orchestrator.parse_referee_winner(raw, "A", "B")
	assert result == "A"


#============================================
def test_parse_referee_winner_fallback():
	"""No <winner> tag found returns label_b."""
	raw = "No tag here at all"
	result = depth_orchestrator.parse_referee_winner(raw, "A", "B")
	assert result == "B"


#============================================
def test_parse_referee_winner_no_match():
	"""Tag content does not match either label; returns label_b."""
	raw = "<winner>Unknown</winner>"
	result = depth_orchestrator.parse_referee_winner(raw, "A", "B")
	assert result == "B"


#============================================
def test_run_depth_pipeline_depth_1(tmp_path):
	"""Depth 1: single draft returned, no referee or polish called."""
	counter = [0]

	def generate_draft_fn():
		counter[0] += 1
		return f"draft_{counter[0]}"

	referee_called = []
	polish_called = []

	def referee_fn(a, b):
		referee_called.append((a, b))
		return "<winner>Draft 1</winner><reason>test</reason>"

	def polish_fn(drafts, depth):
		polish_called.append((drafts, depth))
		return "polished_" + "_".join(drafts)

	def quality_check_fn(text):
		return ""

	result = depth_orchestrator.run_depth_pipeline(
		generate_draft_fn=generate_draft_fn,
		referee_fn=referee_fn,
		polish_fn=polish_fn,
		depth=1,
		cache_dir=str(tmp_path),
		cache_key_prefix="test",
		continue_mode=False,
		max_tokens=1000,
		quality_check_fn=quality_check_fn,
		logger=None,
	)
	assert result == "draft_1"
	assert counter[0] == 1
	assert referee_called == []
	assert polish_called == []


#============================================
def test_run_depth_pipeline_depth_2(tmp_path):
	"""Depth 2: 2 drafts generated, polish called, no referee."""
	counter = [0]

	def generate_draft_fn():
		counter[0] += 1
		return f"draft_{counter[0]}"

	referee_called = []

	def referee_fn(a, b):
		referee_called.append((a, b))
		return "<winner>Draft 1</winner><reason>test</reason>"

	polish_called = []

	def polish_fn(drafts, depth):
		polish_called.append((drafts, depth))
		return "polished_" + "_".join(drafts)

	def quality_check_fn(text):
		return ""

	result = depth_orchestrator.run_depth_pipeline(
		generate_draft_fn=generate_draft_fn,
		referee_fn=referee_fn,
		polish_fn=polish_fn,
		depth=2,
		cache_dir=str(tmp_path),
		cache_key_prefix="test",
		continue_mode=False,
		max_tokens=1000,
		quality_check_fn=quality_check_fn,
		logger=None,
	)
	assert counter[0] == 2
	assert referee_called == []
	assert len(polish_called) == 1
	# polish receives both drafts
	assert polish_called[0] == (["draft_1", "draft_2"], 2)
	assert result == "polished_draft_1_draft_2"


#============================================
def test_run_depth_pipeline_depth_4(tmp_path):
	"""Depth 4: 4 drafts, 2 referee calls, 1 polish call."""
	counter = [0]

	def generate_draft_fn():
		counter[0] += 1
		return f"draft_{counter[0]}"

	referee_called = []

	def referee_fn(a, b):
		referee_called.append((a, b))
		# always pick the first draft (label_a pattern: "Draft N")
		# bracket 0: label_a = "Draft 1", bracket 1: label_a = "Draft 3"
		bracket_idx = len(referee_called) - 1
		label_a = f"Draft {bracket_idx * 2 + 1}"
		return f"<winner>{label_a}</winner><reason>test</reason>"

	polish_called = []

	def polish_fn(drafts, depth):
		polish_called.append((drafts, depth))
		return "polished_" + "_".join(drafts)

	def quality_check_fn(text):
		return ""

	result = depth_orchestrator.run_depth_pipeline(
		generate_draft_fn=generate_draft_fn,
		referee_fn=referee_fn,
		polish_fn=polish_fn,
		depth=4,
		cache_dir=str(tmp_path),
		cache_key_prefix="test",
		continue_mode=False,
		max_tokens=1000,
		quality_check_fn=quality_check_fn,
		logger=None,
	)
	assert counter[0] == 4
	# 2 referee bracket calls
	assert len(referee_called) == 2
	assert referee_called[0] == ("draft_1", "draft_2")
	assert referee_called[1] == ("draft_3", "draft_4")
	# 1 polish call with the 2 referee winners
	assert len(polish_called) == 1
	assert polish_called[0] == (["draft_1", "draft_3"], 4)
	assert result == "polished_draft_1_draft_3"
