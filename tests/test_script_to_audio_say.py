import os
import sys

import pytest

import git_file_utils


REPO_ROOT = git_file_utils.get_repo_root()
PIPELINE_DIR = os.path.join(REPO_ROOT, "pipeline")
if PIPELINE_DIR not in sys.path:
	sys.path.insert(0, PIPELINE_DIR)

import script_to_audio_say


#============================================
def test_parse_script_lines_extracts_role_pairs() -> None:
	"""
	ROLE: text rows should parse to normalized uppercase labels.
	"""
	script_text = "speaker_1: hello there\nSPEAKER_2: Another line\n\n"
	lines = script_to_audio_say.parse_script_lines(script_text)
	assert lines == [
		("SPEAKER_1", "hello there"),
		("SPEAKER_2", "Another line"),
	]


#============================================
def test_build_single_voice_narration_joins_role_lines() -> None:
	"""
	When ROLE lines exist, narration should be text-only sequence.
	"""
	lines = [
		("SPEAKER_1", "alpha"),
		("SPEAKER_2", "beta"),
	]
	result = script_to_audio_say.build_single_voice_narration("ignored", lines)
	assert result == "alpha beta"


#============================================
def test_parse_say_voices_reads_names() -> None:
	"""
	Voice parser should read names including spaces.
	"""
	raw_output = (
		"Alex                en_US    # Most people recognize me by my voice.\n"
		"Bad News            en_US    # Trinoids are not real\n"
	)
	voices = script_to_audio_say.parse_say_voices(raw_output)
	assert voices == ["Alex", "Bad News"]


#============================================
def test_resolve_voice_name_exact_and_siri_alias() -> None:
	"""
	Voice resolver should match exact names and Siri alias.
	"""
	voices = ["Alex", "Siri Voice 4", "Samantha"]
	assert script_to_audio_say.resolve_voice_name("alex", voices) == "Alex"
	assert script_to_audio_say.resolve_voice_name("Siri", voices) == "Siri Voice 4"


#============================================
def test_resolve_voice_name_unknown_raises() -> None:
	"""
	Unknown explicit voice should raise.
	"""
	with pytest.raises(RuntimeError):
		script_to_audio_say.resolve_voice_name("Nope", ["Alex"])
