#!/usr/bin/env python3
"""
Ollama chat transport.
"""

from __future__ import annotations

# Standard Library
import json
import random
import time
import urllib.error
import urllib.request

# local repo modules
from ..errors import TransportUnavailableError


class OllamaTransport:
	name = "Ollama"

	def __init__(
		self,
		model: str,
		base_url: str = "http://localhost:11434",
		system_message: str = "",
		use_history: bool = False,
		max_turns: int = 6,
	) -> None:
		self.model = model
		self.base_url = base_url.rstrip("/")
		self.system_message = system_message
		self.use_history = bool(use_history)
		self.max_turns = int(max_turns)
		self.messages: list[dict[str, str]] = []

	def _build_messages(self, prompt: str) -> list[dict[str, str]]:
		messages: list[dict[str, str]] = []
		if self.system_message:
			messages.append({"role": "system", "content": self.system_message})
		if self.use_history and self.messages:
			messages.extend(self.messages)
		messages.append({"role": "user", "content": prompt})
		return messages

	def _build_messages_from_chat(self, messages: list[dict[str, str]]) -> list[dict[str, str]]:
		combined: list[dict[str, str]] = []
		if self.system_message:
			combined.append({"role": "system", "content": self.system_message})
		if self.use_history and self.messages:
			combined.extend(self.messages)
		combined.extend(messages)
		return combined

	def _last_user_message(self, messages: list[dict[str, str]]) -> str | None:
		for msg in reversed(messages):
			if msg.get("role") == "user":
				content = msg.get("content", "")
				return content if isinstance(content, str) and content else None
		return None

	def _trim_history(self) -> None:
		if not self.use_history:
			return
		if self.max_turns < 1:
			self.messages = []
			return
		max_messages = self.max_turns * 2
		while len(self.messages) > max_messages:
			if len(self.messages) >= 2:
				self.messages = self.messages[2:]
			else:
				self.messages = []
				return

	def _record_history(self, prompt: str, assistant_message: str) -> None:
		if not self.use_history:
			return
		self.messages.append({"role": "user", "content": prompt})
		self.messages.append({"role": "assistant", "content": assistant_message})
		self._trim_history()

	def generate(self, prompt: str, *, purpose: str, max_tokens: int) -> str:
		messages = self._build_messages(prompt)
		payload: dict[str, object] = {
			"model": self.model,
			"messages": messages,
			"stream": False,
			"options": {"num_predict": max_tokens},
		}
		time.sleep(random.random())
		request = urllib.request.Request(
			f"{self.base_url}/api/chat",
			data=json.dumps(payload).encode("utf-8"),
			headers={"Content-Type": "application/json"},
			method="POST",
		)
		try:
			with urllib.request.urlopen(request, timeout=30) as response:
				if response.status >= 400:
					raise RuntimeError(f"Ollama chat error: status {response.status}")
				response_body = response.read()
		except urllib.error.URLError as exc:
			raise TransportUnavailableError("Ollama is unreachable.") from exc
		parsed = json.loads(response_body.decode("utf-8"))
		assistant_message = parsed.get("message", {}).get("content", "")
		if not assistant_message:
			raise RuntimeError("Ollama chat returned empty content")
		self._record_history(prompt, assistant_message)
		return assistant_message

	def generate_chat(
		self,
		messages: list[dict[str, str]],
		*,
		purpose: str,
		max_tokens: int,
	) -> str:
		combined = self._build_messages_from_chat(messages)
		payload: dict[str, object] = {
			"model": self.model,
			"messages": combined,
			"stream": False,
			"options": {"num_predict": max_tokens},
		}
		time.sleep(random.random())
		request = urllib.request.Request(
			f"{self.base_url}/api/chat",
			data=json.dumps(payload).encode("utf-8"),
			headers={"Content-Type": "application/json"},
			method="POST",
		)
		try:
			with urllib.request.urlopen(request, timeout=30) as response:
				if response.status >= 400:
					raise RuntimeError(f"Ollama chat error: status {response.status}")
				response_body = response.read()
		except urllib.error.URLError as exc:
			raise TransportUnavailableError("Ollama is unreachable.") from exc
		parsed = json.loads(response_body.decode("utf-8"))
		assistant_message = parsed.get("message", {}).get("content", "")
		if not assistant_message:
			raise RuntimeError("Ollama chat returned empty content")
		last_user = self._last_user_message(messages)
		if last_user:
			self._record_history(last_user, assistant_message)
		return assistant_message
