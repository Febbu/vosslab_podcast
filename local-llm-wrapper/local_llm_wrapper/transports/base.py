#!/usr/bin/env python3
"""
Transport interface for LLM backends.
"""

from __future__ import annotations

from typing import Protocol


class LLMTransport(Protocol):
	name: str

	def generate(self, prompt: str, *, purpose: str, max_tokens: int) -> str:
		"""
		Send a prompt and return raw model text.
		"""

	# Optional: transports may implement generate_chat(messages, purpose, max_tokens)
