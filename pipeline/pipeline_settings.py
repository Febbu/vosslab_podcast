#!/usr/bin/env python3
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

