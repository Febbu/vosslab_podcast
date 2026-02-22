import os
import sys

import pytest

import git_file_utils


REPO_ROOT = git_file_utils.get_repo_root()
PIPELINE_DIR = os.path.join(REPO_ROOT, "pipeline")
if PIPELINE_DIR not in sys.path:
	sys.path.insert(0, PIPELINE_DIR)

import pipeline_settings


#============================================
def test_load_settings_missing_file(tmp_path) -> None:
	"""
	Missing settings file should return empty settings.
	"""
	settings, resolved_path = pipeline_settings.load_settings(str(tmp_path / "missing.yaml"))
	assert settings == {}
	assert resolved_path.endswith("missing.yaml")


#============================================
def test_load_settings_reads_yaml(tmp_path) -> None:
	"""
	YAML settings should be parsed into nested mapping values.
	"""
	settings_path = tmp_path / "settings.yaml"
	settings_path.write_text(
		"github:\n"
		"  username: alice\n"
		"llm:\n"
		"  transport: apple\n"
		"  max_tokens: 999\n",
		encoding="utf-8",
	)
	settings, _ = pipeline_settings.load_settings(str(settings_path))
	assert pipeline_settings.get_setting_str(settings, ["github", "username"], "") == "alice"
	assert pipeline_settings.get_setting_str(settings, ["llm", "transport"], "ollama") == "apple"
	assert pipeline_settings.get_setting_int(settings, ["llm", "max_tokens"], 1200) == 999


#============================================
def test_get_setting_int_invalid_value_raises() -> None:
	"""
	Invalid integer setting should raise RuntimeError.
	"""
	settings = {"llm": {"max_tokens": "abc"}}
	with pytest.raises(RuntimeError):
		pipeline_settings.get_setting_int(settings, ["llm", "max_tokens"], 1200)
