import os
import sys

import pytest

import git_file_utils


REPO_ROOT = git_file_utils.get_repo_root()
PIPELINE_DIR = os.path.join(REPO_ROOT, "pipeline")
if PIPELINE_DIR not in sys.path:
	sys.path.insert(0, PIPELINE_DIR)

from podlib import pipeline_settings


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
		"  max_tokens: 999\n",
		encoding="utf-8",
	)
	settings, _ = pipeline_settings.load_settings(str(settings_path))
	assert pipeline_settings.get_setting_str(settings, ["github", "username"], "") == "alice"
	assert pipeline_settings.get_setting_int(settings, ["llm", "max_tokens"], 1200) == 999


#============================================
def test_get_setting_int_invalid_value_raises() -> None:
	"""
	Invalid integer setting should raise RuntimeError.
	"""
	settings = {"llm": {"max_tokens": "abc"}}
	with pytest.raises(RuntimeError):
		pipeline_settings.get_setting_int(settings, ["llm", "max_tokens"], 1200)


#============================================
def test_get_enabled_llm_transport_single_enabled() -> None:
	"""
	Exactly one enabled provider should be selected.
	"""
	settings = {
		"llm": {
			"providers": {
				"apple": {"enabled": True},
				"ollama": {"enabled": False},
			}
		}
	}
	transport = pipeline_settings.get_enabled_llm_transport(settings)
	assert transport == "apple"


#============================================
def test_get_enabled_llm_transport_multiple_enabled_raises() -> None:
	"""
	More than one enabled provider should raise RuntimeError.
	"""
	settings = {
		"llm": {
			"providers": {
				"apple": {"enabled": True},
				"ollama": {"enabled": True},
			}
		}
	}
	with pytest.raises(RuntimeError):
		pipeline_settings.get_enabled_llm_transport(settings)


#============================================
def test_get_llm_provider_model_apple_is_empty() -> None:
	"""
	Apple provider should not require a model.
	"""
	settings = {
		"llm": {
			"providers": {
				"apple": {"enabled": True},
			},
		}
	}
	model = pipeline_settings.get_llm_provider_model(settings, "apple")
	assert model == ""


#============================================
def test_get_enabled_llm_transport_falls_back_to_legacy_value() -> None:
	"""
	Legacy llm.transport is used when providers are not enabled.
	"""
	settings = {"llm": {"transport": "ollama", "providers": {}}}
	transport = pipeline_settings.get_enabled_llm_transport(settings)
	assert transport == "ollama"


#============================================
def test_get_llm_provider_model_ollama_single_enabled_model() -> None:
	"""
	Enabled Ollama model should be selected from model list.
	"""
	settings = {
		"llm": {
			"providers": {
				"ollama": {
					"enabled": True,
					"models": [
						{"name": "qwen2.5:7b", "enabled": True},
						{"name": "llama3.2:3b", "enabled": False},
					],
				},
			},
		}
	}
	model = pipeline_settings.get_llm_provider_model(settings, "ollama")
	assert model == "qwen2.5:7b"


#============================================
def test_get_llm_provider_model_ollama_multiple_enabled_raises() -> None:
	"""
	More than one enabled Ollama model should raise RuntimeError.
	"""
	settings = {
		"llm": {
			"providers": {
				"ollama": {
					"enabled": True,
					"models": [
						{"name": "qwen2.5:7b", "enabled": True},
						{"name": "llama3.2:3b", "enabled": True},
					],
				},
			},
		}
	}
	with pytest.raises(RuntimeError):
		pipeline_settings.get_llm_provider_model(settings, "ollama")


#============================================
def test_get_llm_provider_model_ollama_none_enabled_raises() -> None:
	"""
	No enabled Ollama model should raise RuntimeError.
	"""
	settings = {
		"llm": {
			"providers": {
				"ollama": {
					"enabled": True,
					"models": [
						{"name": "qwen2.5:7b", "enabled": False},
						{"name": "llama3.2:3b", "enabled": False},
					],
				},
			},
		}
	}
	with pytest.raises(RuntimeError):
		pipeline_settings.get_llm_provider_model(settings, "ollama")
