#!/usr/bin/env python3
"""
Standardized exception types for the LLM wrapper.
"""

from __future__ import annotations

#============================================


class LLMError(RuntimeError):
	"""
	Base class for LLM wrapper errors.
	"""


class TransportUnavailableError(LLMError):
	"""
	Raised when a transport cannot be used on this machine.
	"""


class ContextWindowError(LLMError):
	"""
	Raised when the prompt exceeds a model context window.
	"""


class GuardrailRefusalError(LLMError):
	"""
	Raised when a model refuses a prompt due to safety/guardrails.
	"""
