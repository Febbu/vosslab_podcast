import os

import yaml


#============================================
def get_repo_root() -> str:
	"""
	Return repository root based on this module location.
	"""
	module_dir = os.path.dirname(os.path.abspath(__file__))
	repo_root = os.path.dirname(module_dir)
	return repo_root


#============================================
def resolve_settings_path(path_text: str) -> str:
	"""
	Resolve settings path against cwd first, then repo root.
	"""
	if os.path.isabs(path_text):
		return path_text
	cwd_candidate = os.path.abspath(path_text)
	if os.path.isfile(cwd_candidate):
		return cwd_candidate
	repo_root = get_repo_root()
	repo_candidate = os.path.join(repo_root, path_text)
	return os.path.abspath(repo_candidate)


#============================================
def load_settings(path_text: str) -> tuple[dict, str]:
	"""
	Load YAML settings dict and return it with resolved path.
	"""
	resolved_path = resolve_settings_path(path_text)
	if not os.path.isfile(resolved_path):
		return {}, resolved_path
	with open(resolved_path, "r", encoding="utf-8") as handle:
		data = yaml.safe_load(handle.read())
	if data is None:
		return {}, resolved_path
	if not isinstance(data, dict):
		raise RuntimeError(f"Settings file must contain a mapping: {resolved_path}")
	return data, resolved_path


#============================================
def get_nested_value(settings: dict, keys: list[str], default_value):
	"""
	Read nested mapping value by key path.
	"""
	current = settings
	for key in keys:
		if not isinstance(current, dict):
			return default_value
		if key not in current:
			return default_value
		current = current[key]
	return current


#============================================
def get_setting_str(settings: dict, keys: list[str], default_value: str) -> str:
	"""
	Read a string setting from nested path with fallback.
	"""
	value = get_nested_value(settings, keys, default_value)
	if value is None:
		return default_value
	return str(value).strip()


#============================================
def get_setting_int(settings: dict, keys: list[str], default_value: int) -> int:
	"""
	Read an integer setting from nested path with fallback.
	"""
	value = get_nested_value(settings, keys, default_value)
	if value is None:
		return default_value
	try:
		return int(value)
	except ValueError as error:
		raise RuntimeError(f"Invalid integer for setting path {'.'.join(keys)}: {value}") from error


#============================================
def get_setting_bool(settings: dict, keys: list[str], default_value: bool) -> bool:
	"""
	Read a boolean setting from nested path with fallback.
	"""
	value = get_nested_value(settings, keys, default_value)
	if isinstance(value, bool):
		return value
	if isinstance(value, str):
		text = value.strip().lower()
		if text in {"1", "true", "yes", "on"}:
			return True
		if text in {"0", "false", "no", "off"}:
			return False
		raise RuntimeError(f"Invalid boolean for setting path {'.'.join(keys)}: {value}")
	if isinstance(value, int):
		return value != 0
	if value is None:
		return default_value
	raise RuntimeError(f"Invalid boolean for setting path {'.'.join(keys)}: {value}")


#============================================
def get_github_username(settings: dict, default_value: str = "vosslab") -> str:
	"""
	Resolve GitHub username from settings with fallback.
	"""
	value = get_setting_str(settings, ["github", "username"], "").strip()
	if value:
		return value
	return default_value


#============================================
def resolve_user_scoped_out_path(path_text: str, default_path_text: str, user: str) -> str:
	"""
	Scope default out/ paths under out/<user>/ while preserving custom paths.
	"""
	path_value = (path_text or "").strip()
	default_value = (default_path_text or "").strip()
	if path_value != default_value:
		return path_value
	if not default_value.startswith("out/"):
		return path_value
	tail = default_value[len("out/"):].lstrip("/")
	user_value = (user or "").strip() or "vosslab"
	return os.path.join("out", user_value, tail)


#============================================
def get_enabled_llm_transport(settings: dict) -> str:
	"""
	Resolve exactly one enabled LLM provider from settings.
	"""
	providers = get_nested_value(settings, ["llm", "providers"], {})
	if not isinstance(providers, dict):
		raise RuntimeError("Invalid settings: llm.providers must be a mapping.")

	enabled = []
	for provider_name, provider_config in providers.items():
		if not isinstance(provider_config, dict):
			continue
		enabled_value = provider_config.get("enabled", False)
		enabled_flag = get_setting_bool(
			{"provider": {"enabled": enabled_value}},
			["provider", "enabled"],
			False,
		)
		if enabled_flag:
			enabled.append(provider_name)

	if len(enabled) > 1:
		raise RuntimeError(
			"Only one LLM provider may be enabled in settings.yaml. "
			+ f"Enabled providers: {', '.join(enabled)}"
		)
	if len(enabled) == 1:
		return enabled[0]

	legacy_transport = get_setting_str(settings, ["llm", "transport"], "").strip()
	if legacy_transport:
		return legacy_transport
	raise RuntimeError(
		"No enabled LLM provider found in settings.yaml. "
		+ "Set llm.providers.<name>.enabled to true."
	)


#============================================
def get_llm_provider_model(settings: dict, provider_name: str) -> str:
	"""
	Read default model for one provider from settings.
	"""
	if provider_name == "apple":
		return ""
	if provider_name != "ollama":
		model_value = get_setting_str(
			settings,
			["llm", "providers", provider_name, "model"],
			"",
		)
		if model_value:
			return model_value
		return get_setting_str(settings, ["llm", "model"], "")

	model_entries = get_nested_value(
		settings,
		["llm", "providers", "ollama", "models"],
		[],
	)
	if not model_entries:
		model_value = get_setting_str(
			settings,
			["llm", "providers", "ollama", "model"],
			"",
		)
		if model_value:
			return model_value
		return get_setting_str(settings, ["llm", "model"], "")
	if not isinstance(model_entries, list):
		raise RuntimeError("Invalid settings: llm.providers.ollama.models must be a list.")

	enabled_models = []
	for model_entry in model_entries:
		if not isinstance(model_entry, dict):
			continue
		model_name = str(model_entry.get("name", "")).strip()
		if not model_name:
			continue
		enabled_flag = get_setting_bool(
			{"model": {"enabled": model_entry.get("enabled", False)}},
			["model", "enabled"],
			False,
		)
		if enabled_flag:
			enabled_models.append(model_name)

	if len(enabled_models) > 1:
		raise RuntimeError(
			"Only one Ollama model may be enabled in settings.yaml. "
			+ f"Enabled models: {', '.join(enabled_models)}"
		)
	if len(enabled_models) == 1:
		return enabled_models[0]
	raise RuntimeError(
		"No enabled Ollama model found in settings.yaml. "
		+ "Set exactly one llm.providers.ollama.models[].enabled to true."
	)
