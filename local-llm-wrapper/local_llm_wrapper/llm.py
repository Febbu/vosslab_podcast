#!/usr/bin/env python3
"""
Compatibility exports for LLM utilities and engine.
"""

from __future__ import annotations

from .errors import (
	ContextWindowError,
	GuardrailRefusalError,
	LLMError,
	TransportUnavailableError,
)
from .llm_client import LLMClient
from .llm_parsers import RenameResult, SortResult
from .llm_utils import (
	apple_models_available,
	get_vram_size_in_gb as _get_vram_size_in_gb,
	total_ram_bytes as _total_ram_bytes,
	sanitize_filename,
)
from .transports.apple import AppleTransport
from .transports.ollama import OllamaTransport

def get_vram_size_in_gb() -> int | None:
	return _get_vram_size_in_gb()


def total_ram_bytes() -> int:
	return _total_ram_bytes()


def choose_model(model_override: str | None) -> str:
	"""
	Compatibility wrapper so tests can monkeypatch get_vram_size_in_gb/total_ram_bytes.
	"""
	from .llm_utils import choose_model as _choose_model

	original_vram = _get_vram_size_in_gb
	original_ram = _total_ram_bytes

	def _patched_vram() -> int | None:
		return get_vram_size_in_gb()

	def _patched_ram() -> int:
		return total_ram_bytes()

	try:
		globals_dict = _choose_model.__globals__
		globals_dict["get_vram_size_in_gb"] = _patched_vram
		globals_dict["total_ram_bytes"] = _patched_ram
		return _choose_model(model_override)
	finally:
		globals_dict = _choose_model.__globals__
		globals_dict["get_vram_size_in_gb"] = original_vram
		globals_dict["total_ram_bytes"] = original_ram


__all__ = [
	"LLMError",
	"TransportUnavailableError",
	"ContextWindowError",
	"GuardrailRefusalError",
	"LLMClient",
	"RenameResult",
	"SortResult",
	"apple_models_available",
	"choose_model",
	"sanitize_filename",
	"AppleTransport",
	"OllamaTransport",
]
