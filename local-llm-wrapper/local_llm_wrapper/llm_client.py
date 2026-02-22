#!/usr/bin/env python3
"""
Public client wrapper for the local LLM engine.
"""

from __future__ import annotations

# local repo modules
from .llm_engine import LLMEngine
from .llm_parsers import RenameResult, SortResult
from .llm_prompts import SortItem
from .transports.base import LLMTransport

#============================================


class LLMClient:
	"""
	Public entry point for local LLM usage.
	"""

	def __init__(
		self,
		transports: list[LLMTransport],
		*,
		context: str | None = None,
		quiet: bool = False,
	) -> None:
		self._engine = LLMEngine(
			transports=transports,
			context=context,
			quiet=quiet,
		)

	#============================================
	def generate(
		self,
		prompt: str | None = None,
		*,
		messages: list[dict[str, str]] | None = None,
		purpose: str | None = None,
		max_tokens: int = 1200,
	) -> str:
		return self._engine.generate(
			prompt,
			messages=messages,
			purpose=purpose,
			max_tokens=max_tokens,
		)

	#============================================
	def rename(self, current_name: str, metadata: dict) -> RenameResult:
		return self._engine.rename(current_name, metadata)

	#============================================
	def sort(self, files: list[SortItem | dict]) -> SortResult:
		items: list[SortItem] = []
		for item in files:
			if isinstance(item, SortItem):
				items.append(item)
				continue
			if isinstance(item, dict):
				required_keys = ("path", "name", "ext", "description")
				for key in required_keys:
					if key not in item:
						raise ValueError(
							"Sort items require path, name, ext, and description."
						)
				path = item["path"]
				name = item["name"]
				ext = item["ext"]
				description = item["description"]
				items.append(
					SortItem(
						path=path,
						name=name,
						ext=ext,
						description=description,
					)
				)
				continue
			raise TypeError("Sort items must be SortItem or dict.")
		return self._engine.sort(items)
