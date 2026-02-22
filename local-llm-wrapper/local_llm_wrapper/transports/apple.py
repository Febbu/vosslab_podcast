#!/usr/bin/env python3
"""
Apple Foundation Models transport.
"""

from __future__ import annotations

# Standard Library
import platform
import time

# local repo modules
from ..errors import GuardrailRefusalError, TransportUnavailableError
from ..llm_utils import MIN_MACOS_MAJOR, _parse_macos_version


class AppleTransport:
	name = "AppleLLM"

	def __init__(
		self,
		instructions: str | None = None,
		max_retries: int = 2,
		temperature: float = 0.2,
	) -> None:
		self.instructions = instructions
		self.max_retries = max(1, int(max_retries))
		self.temperature = float(temperature)

	def _require_apple_intelligence(self) -> None:
		try:
			from applefoundationmodels import Session, apple_intelligence_available
		except Exception as exc:
			raise TransportUnavailableError(
				"apple-foundation-models is required for the Apple backend."
			) from exc
		arch = platform.machine().lower()
		if arch != "arm64":
			raise TransportUnavailableError(
				"Apple Intelligence requires Apple Silicon (arm64)."
			)
		major, minor, patch = _parse_macos_version()
		if major < MIN_MACOS_MAJOR:
			raise TransportUnavailableError(
				f"macOS {MIN_MACOS_MAJOR}.0+ is required (detected {major}.{minor}.{patch})."
			)
		if not apple_intelligence_available():
			try:
				reason = Session.get_availability_reason()
			except Exception:
				reason = "Apple Intelligence not available or not enabled."
			raise TransportUnavailableError(str(reason))

	def generate(self, prompt: str, *, purpose: str, max_tokens: int) -> str:
		self._require_apple_intelligence()
		from applefoundationmodels import Session
		from applefoundationmodels.exceptions import GuardrailViolationError

		default_instructions = (
			"Follow the prompt precisely. "
			"If the prompt requests XML tags, output only those tags and nothing else."
		)
		session_instructions = self.instructions or default_instructions
		last_error: Exception | None = None
		for attempt in range(1, self.max_retries + 1):
			try:
				with Session(instructions=session_instructions) as session:
					response = session.generate(
						prompt,
						max_tokens=max_tokens,
						temperature=self.temperature,
					)
				return response.text.strip()
			except GuardrailViolationError as exc:
				raise GuardrailRefusalError(str(exc)) from exc
			except Exception as exc:
				last_error = exc
				if attempt < self.max_retries:
					time.sleep(attempt)
					continue
				raise RuntimeError("Apple LLM call failed.") from exc
		if last_error:
			raise RuntimeError("Apple LLM call failed.") from last_error
		raise RuntimeError("Apple LLM call failed.")
