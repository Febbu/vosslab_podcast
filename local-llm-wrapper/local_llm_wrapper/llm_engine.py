#!/usr/bin/env python3
"""
Backend-agnostic LLM engine with fallback and strict parsing.
"""

from __future__ import annotations

# Standard Library
from dataclasses import dataclass

# local repo modules
from .errors import TransportUnavailableError
from .llm_parsers import ParseError, KeepResult, RenameResult, SortResult, parse_keep_response, parse_rename_response, parse_sort_response
from .llm_prompts import (
	KeepRequest,
	RenameRequest,
	SortItem,
	SortRequest,
	RENAME_EXAMPLE_OUTPUT,
	KEEP_EXAMPLE_OUTPUT,
	SORT_EXAMPLE_OUTPUT,
	build_format_fix_prompt,
	build_keep_prompt,
	build_rename_prompt,
	build_rename_prompt_minimal,
	build_sort_prompt,
)
from .llm_utils import (
	compute_stem_features,
	_ensure_text_prompt,
	_ensure_chat_messages,
	format_chat_prompt,
	_is_guardrail_error,
	_is_context_window_error,
	_print_llm,
	log_parse_failure,
	normalize_reason,
	sanitize_filename,
)
from .transports.base import LLMTransport

#============================================


@dataclass(slots=True)
class LLMEngine:
	transports: list[LLMTransport]
	context: str | None = None
	quiet: bool = False

	#============================================
	def generate(
		self,
		prompt: str | None = None,
		*,
		messages: list[dict[str, str]] | None = None,
		purpose: str | None = None,
		max_tokens: int = 1200,
	) -> str:
		if prompt is None and messages is None:
			raise ValueError("Prompt or messages are required.")
		if prompt is not None and messages is not None:
			raise ValueError("Provide prompt or messages, not both.")
		text_prompt: str | None = None
		chat_messages: list[dict[str, str]] | None = None
		if messages is not None:
			chat_messages = _ensure_chat_messages(messages)
		else:
			text_prompt = _ensure_text_prompt(prompt)
		return self._generate_with_fallback(
			text_prompt,
			messages=chat_messages,
			purpose=purpose or "general response",
			max_tokens=max_tokens,
			retry_prompt=None,
		)

	#============================================
	def rename(self, current_name: str, metadata: dict) -> RenameResult:
		req = RenameRequest(metadata=metadata, current_name=current_name, context=self.context)
		prompt = build_rename_prompt(req)
		raw = self._generate_with_fallback(
			prompt,
			messages=None,
			purpose="filename based on content",
			max_tokens=200,
			retry_prompt=build_rename_prompt_minimal(req),
		)
		result = self._parse_with_retry(
			lambda text: parse_rename_response(text),
			prompt,
			RENAME_EXAMPLE_OUTPUT,
			raw,
			purpose="filename based on content",
			max_tokens=200,
		)
		result.new_name = sanitize_filename(result.new_name)
		result.reason = normalize_reason(result.reason)
		return result

	#============================================
	def stem_action(self, original_stem: str, suggested_name: str, extension: str | None = None) -> KeepResult:
		features = compute_stem_features(original_stem, suggested_name)
		req = KeepRequest(
			original_stem=original_stem,
			suggested_name=suggested_name,
			extension=extension,
			features=features,
		)
		prompt = build_keep_prompt(req)
		raw = self._generate_with_fallback(
			prompt,
			messages=None,
			purpose="how to handle the original filename stem",
			max_tokens=120,
			retry_prompt=None,
		)
		result = self._parse_with_retry(
			lambda text: parse_keep_response(text, original_stem),
			prompt,
			KEEP_EXAMPLE_OUTPUT,
			raw,
			purpose="how to handle the original filename stem",
			max_tokens=120,
		)
		result.reason = normalize_reason(result.reason)
		return result

	#============================================
	def sort(self, files: list[SortItem]) -> SortResult:
		if not files:
			return SortResult(assignments={}, raw_text="")
		assignments: dict[str, str] = {}
		reasons: dict[str, str] = {}
		last_raw = ""
		for item in files:
			req = SortRequest(files=[item], context=self.context)
			prompt = build_sort_prompt(req)
			raw = self._generate_with_fallback(
				prompt,
				messages=None,
				purpose="category assignment",
				max_tokens=120,
				retry_prompt=None,
			)
			result = self._parse_with_retry(
				lambda text: parse_sort_response(text, [item.path]),
				prompt,
				SORT_EXAMPLE_OUTPUT,
				raw,
				purpose="category assignment",
				max_tokens=120,
			)
			assignments.update(result.assignments)
			for path, reason in result.reasons.items():
				reasons[path] = normalize_reason(reason)
			last_raw = result.raw_text
		return SortResult(assignments=assignments, reasons=reasons, raw_text=last_raw)

	#============================================
	def _generate_with_fallback(
		self,
		prompt: str | None,
		*,
		messages: list[dict[str, str]] | None,
		purpose: str,
		max_tokens: int,
		retry_prompt: str | None,
	) -> str:
		last_exc: Exception | None = None
		for idx, transport in enumerate(self.transports):
			try:
				if not self.quiet:
					_print_llm(f"asking {transport.name} for {purpose}")
				return self._generate_on_transport(
					transport,
					prompt,
					messages,
					purpose,
					max_tokens,
				)
			except Exception as exc:
				last_exc = exc
				if isinstance(exc, TransportUnavailableError):
					continue
				if _is_guardrail_error(exc) or _is_context_window_error(exc):
					if retry_prompt and idx == 0:
						try:
							if not self.quiet:
								_print_llm(
									f"retrying {transport.name} with minimal prompt for {purpose}"
								)
							return self._generate_on_transport(
								transport,
								retry_prompt,
								None,
								purpose,
								max_tokens,
							)
						except Exception as retry_exc:
							last_exc = retry_exc
							if _is_guardrail_error(retry_exc) or _is_context_window_error(retry_exc):
								continue
							raise
					continue
				raise
		if last_exc:
			raise last_exc
		raise TransportUnavailableError("No LLM transports available.")

	#============================================
	def _parse_with_retry(
		self,
		parser,
		original_prompt: str,
		example_output: str,
		raw_text: str,
		*,
		purpose: str,
		max_tokens: int,
	):
		try:
			return parser(raw_text)
		except ParseError as exc:
			excerpt = " ".join(raw_text.split())[:160]
			if not self.quiet:
				print(f"[WHY] parse_error: {exc} (excerpt: {excerpt})")
			log_parse_failure(
				purpose=purpose,
				error=exc,
				raw_text=exc.raw_text or raw_text,
				prompt=original_prompt,
				stage="initial",
			)
			fix_prompt = build_format_fix_prompt(original_prompt, example_output)
			last_parse: ParseError | None = None
			last_transport: Exception | None = None
			last_fixed: str | None = None
			for transport in self.transports:
				try:
					if not self.quiet:
						_print_llm(f"asking {transport.name} for {purpose} (format fix)")
					fixed = self._generate_on_transport(
						transport,
						fix_prompt,
						None,
						f"{purpose} (format fix)",
						max_tokens,
					)
					last_fixed = fixed
				except Exception as transport_exc:
					if _is_guardrail_error(transport_exc):
						last_transport = transport_exc
						continue
					last_transport = transport_exc
					continue
				try:
					return parser(fixed)
				except ParseError as parse_exc:
					last_parse = parse_exc
					log_parse_failure(
						purpose=purpose,
						error=parse_exc,
						raw_text=parse_exc.raw_text or fixed,
						prompt=fix_prompt,
						stage=f"format fix ({transport.name})",
					)
					continue
			if last_parse:
				text = last_fixed or raw_text
				raise ParseError(str(last_parse), raw_text=text)
			if last_transport:
				raise last_transport
			raise ParseError("Format-fix retry failed.")

	#============================================
	def _generate_on_transport(
		self,
		transport: LLMTransport,
		prompt: str | None,
		messages: list[dict[str, str]] | None,
		purpose: str,
		max_tokens: int,
	) -> str:
		if messages is not None:
			generate_chat = getattr(transport, "generate_chat", None)
			if callable(generate_chat):
				return generate_chat(messages, purpose=purpose, max_tokens=max_tokens)
			prompt = format_chat_prompt(messages)
		if prompt is None:
			raise ValueError("Prompt or messages are required.")
		return transport.generate(prompt, purpose=purpose, max_tokens=max_tokens)
