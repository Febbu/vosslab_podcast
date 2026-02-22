#!/usr/bin/env python3
"""
Shared LLM helpers (backend-agnostic).
"""

from __future__ import annotations

# Standard Library
from datetime import datetime, timezone
import os
import platform
import re
import subprocess
import sys

# local repo modules
from .errors import ContextWindowError, GuardrailRefusalError

#============================================


MAX_FILENAME_CHARS = 100
PROMPT_FILENAME_CHARS = 80
MIN_MACOS_MAJOR = 26
ALLOWED_CATEGORIES = [
	"Document",
	"Spreadsheet",
	"Presentation",
	"Image",
	"Audio",
	"Video",
	"Code",
	"Data",
	"Project",
	"Other",
]
_PLACEHOLDER_REASONS = {
	"short justification",
	"short reason",
	"one sentence. refer to one feature flag.",
	"optional",
	"n/a",
	"na",
}
_NONPRINTABLE_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
_PROMPT_MAX_TOKEN_LEN = 40
_PROMPT_EXCERPT_CHARS = 240
_UUID_RE = re.compile(
	r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$"
)
_HEX_BLOB_RE = re.compile(r"\b[0-9a-fA-F]{8,}\b")
_LONG_DIGIT_RUN_RE = re.compile(r"\d{8,}")
_TOKEN_SPLIT_RE = re.compile(r"[-_.\s]+")
_GENERIC_LABEL_RE = re.compile(
	r"^(img|dsc|scan|screenshot|document|download|file|image|photo|picture)[-_ .]*\d+$",
	re.IGNORECASE,
)
_ALLOWED_CHAT_ROLES = {"system", "user", "assistant"}

_GUARDRAIL_ERRORS: tuple[type[BaseException], ...] = ()
try:
	from applefoundationmodels.exceptions import GuardrailViolationError

	_GUARDRAIL_ERRORS = (GuardrailViolationError,)
except Exception:
	_GUARDRAIL_ERRORS = ()


def _print_llm(label: str) -> None:
	if sys.stdout.isatty():
		print(f"\033[36m[LLM]\033[0m {label}")
	else:
		print(f"[LLM] {label}")


def _ensure_text_prompt(prompt: object) -> str:
	"""
	Ensure prompts are plain text, not bytes or file paths.
	"""
	if isinstance(prompt, bytes):
		raise TypeError("Prompt must be text, not bytes.")
	if isinstance(prompt, os.PathLike):
		raise TypeError("Prompt must be text, not a file path.")
	if not isinstance(prompt, str):
		raise TypeError("Prompt must be text.")
	return prompt


def _ensure_chat_messages(messages: object) -> list[dict[str, str]]:
	"""
	Validate chat messages and return a sanitized list.
	"""
	if not isinstance(messages, (list, tuple)):
		raise TypeError("Chat messages must be a list.")
	cleaned: list[dict[str, str]] = []
	for msg in messages:
		if not isinstance(msg, dict):
			raise TypeError("Chat messages must contain dict items.")
		if "role" not in msg or "content" not in msg:
			raise ValueError("Chat messages must include role and content.")
		role = str(msg["role"]).strip().lower()
		if role not in _ALLOWED_CHAT_ROLES:
			raise ValueError(f"Unsupported chat role: {role}")
		content = msg["content"]
		if not isinstance(content, str):
			raise TypeError("Chat message content must be text.")
		sanitized = _sanitize_prompt_text(content)
		if not sanitized:
			raise ValueError("Chat message content is empty.")
		cleaned.append({"role": role, "content": sanitized})
	if not cleaned:
		raise ValueError("Chat messages are empty.")
	return cleaned


def format_chat_prompt(messages: list[dict[str, str]]) -> str:
	"""
	Format chat messages into a text prompt for completion-style backends.
	"""
	cleaned = _ensure_chat_messages(messages)
	lines: list[str] = []
	for msg in cleaned:
		label = msg["role"].capitalize()
		lines.append(f"{label}: {msg['content']}")
	if cleaned[-1]["role"] != "assistant":
		lines.append("Assistant:")
	return "\n".join(lines).strip()


def log_parse_failure(
	*,
	purpose: str,
	error: Exception,
	raw_text: str,
	prompt: str | None = None,
	stage: str | None = None,
	log_path: str = "XML_PARSE_FAILURES.log",
	max_chars: int = 8000,
) -> None:
	"""
	Append parse failures to a log file for later review.
	"""
	try:
		timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
		parts = ["=" * 80, f"timestamp: {timestamp}", f"purpose: {purpose}"]
		if stage:
			parts.append(f"stage: {stage}")
		parts.append(f"error: {error.__class__.__name__}: {error}")
		if prompt is not None:
			prompt_text = prompt.strip()
			if len(prompt_text) > max_chars:
				prompt_text = prompt_text[:max_chars].rstrip() + "\n...[truncated]..."
			parts.append("prompt:")
			parts.append(prompt_text)
		raw = (raw_text or "").strip()
		if len(raw) > max_chars:
			raw = raw[:max_chars].rstrip() + "\n...[truncated]..."
		parts.append("raw_response:")
		parts.append(raw)
		parts.append("")
		with open(log_path, "a", encoding="utf-8", errors="replace") as handle:
			handle.write("\n".join(parts))
	except Exception:
		return


#============================================


def sanitize_filename(name: str) -> str:
	"""
	Sanitize filename for macOS.
	"""
	allowed = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789.-_"
	result_chars: list[str] = []
	for ch in name:
		if ch.isspace():
			result_chars.append("-")
		elif ch in allowed:
			result_chars.append(ch)
		else:
			result_chars.append("-")
	cleaned = "".join(result_chars)
	while "--" in cleaned:
		cleaned = cleaned.replace("--", "-")
	while "__" in cleaned:
		cleaned = cleaned.replace("__", "_")
	cleaned = cleaned.strip("-_.")
	if len(cleaned) > MAX_FILENAME_CHARS:
		cleaned = cleaned[:MAX_FILENAME_CHARS]
	return cleaned or "file"


def normalize_reason(reason: str | None) -> str:
	"""
	Normalize trivial placeholder reasons to empty string.
	"""
	if not reason:
		return ""
	cleaned = " ".join(str(reason).split())
	lower = cleaned.lower().strip()
	plain = re.sub(r"[^a-z0-9 ]+", "", lower).strip()
	if lower in _PLACEHOLDER_REASONS or plain in _PLACEHOLDER_REASONS:
		return ""
	if "short justification" in lower or "short reason" in lower:
		if "original_stem=" not in lower and "feature_flag" not in lower:
			return ""
	if "justification" in lower and len(lower.split()) <= 3:
		return ""
	return cleaned


def _sanitize_prompt_text(
	value: object,
	max_token_len: int = _PROMPT_MAX_TOKEN_LEN,
	max_chars: int | None = None,
) -> str:
	if value is None:
		return ""
	text = str(value)
	if not text:
		return ""
	text = text.replace("\r\n", "\n").replace("\r", "\n")
	text = text.replace("```", " ")
	text = _NONPRINTABLE_RE.sub(" ", text)
	text = text.replace("\t", " ")
	lines: list[str] = []
	seen: set[str] = set()
	for raw in text.splitlines():
		compact = " ".join(raw.split())
		if not compact:
			continue
		tokens = [token for token in compact.split(" ") if len(token) <= max_token_len]
		if not tokens:
			continue
		line = " ".join(tokens)
		key = line.lower()
		if key in seen:
			continue
		seen.add(key)
		lines.append(line)
	result = "\n".join(lines)
	if max_chars and len(result) > max_chars:
		return result[:max_chars].rstrip()
	return result


def _sanitize_prompt_list(value: object) -> list[str]:
	if value is None:
		return []
	if isinstance(value, (list, tuple, set)):
		cleaned: list[str] = []
		for item in value:
			text = _sanitize_prompt_text(item)
			if text:
				cleaned.append(text)
		return cleaned
	text = _sanitize_prompt_text(value)
	return [text] if text else []


def _prompt_excerpt(metadata: dict) -> str:
	for key in ("summary", "description", "caption", "ocr_text"):
		text = _sanitize_prompt_text(metadata.get(key))
		if text:
			if len(text) > _PROMPT_EXCERPT_CHARS:
				return text[: _PROMPT_EXCERPT_CHARS - 3].rstrip() + "..."
			return text
	return ""


#============================================


def compute_stem_features(original_stem: str, suggested_name: str) -> dict[str, object]:
	"""
	Compute deterministic features for keep-original decisions.
	"""
	stem = original_stem.strip()
	alnum = re.sub(r"[^A-Za-z0-9]", "", stem)
	alnum_length = len(alnum)
	digits = sum(ch.isdigit() for ch in alnum)
	letters = sum(ch.isalpha() for ch in alnum)
	digit_ratio = digits / max(1, alnum_length)
	tokens = [t for t in _TOKEN_SPLIT_RE.split(stem) if t]
	alpha_token_count = sum(1 for t in tokens if any(ch.isalpha() for ch in t))
	token_count = len(tokens)
	has_letter = letters > 0
	is_numeric_only = bool(stem) and stem.isdigit()
	long_digit_run = bool(_LONG_DIGIT_RUN_RE.search(stem))
	uuid_like = bool(_UUID_RE.match(stem))
	hex_blob = bool(_HEX_BLOB_RE.search(stem))
	generic_label = bool(_GENERIC_LABEL_RE.match(stem))
	stem_in_suggested = stem.lower() in suggested_name.lower() if stem and suggested_name else False
	return {
		"has_letter": has_letter,
		"alpha_token_count": alpha_token_count,
		"token_count": token_count,
		"is_numeric_only": is_numeric_only,
		"long_digit_run": long_digit_run,
		"digit_ratio": round(digit_ratio, 3),
		"uuid_like": uuid_like,
		"hex_blob": hex_blob,
		"generic_label": generic_label,
		"length": len(stem),
		"alnum_length": alnum_length,
		"stem_in_suggested": stem_in_suggested,
	}


def extract_xml_tag_content(raw_text: str, tag: str) -> str:
	"""
	Extract the last occurrence of a given XML-like tag.
	"""
	if not raw_text:
		return ""
	lower = raw_text.lower()
	open_token = f"<{tag}"
	close_token = f"</{tag}"
	start_idx = lower.rfind(open_token)
	if start_idx == -1:
		return ""
	gt_idx = raw_text.find(">", start_idx)
	if gt_idx == -1:
		return ""
	close_idx = lower.find(close_token, gt_idx + 1)
	if close_idx == -1:
		content = raw_text[gt_idx + 1 :]
		return content.strip()
	content = raw_text[gt_idx + 1 : close_idx]
	return content.strip()


def _parse_macos_version() -> tuple[int, int, int]:
	version_str = platform.mac_ver()[0]
	parts = [int(p) for p in version_str.split(".") if p.isdigit()]
	while len(parts) < 3:
		parts.append(0)
	if len(parts) >= 3:
		return parts[0], parts[1], parts[2]
	return 0, 0, 0


def apple_models_available() -> bool:
	try:
		from applefoundationmodels import Session, apple_intelligence_available
	except Exception:
		return False
	arch = platform.machine().lower()
	if arch != "arm64":
		return False
	major, _minor, _patch = _parse_macos_version()
	if major < MIN_MACOS_MAJOR:
		return False
	try:
		if not apple_intelligence_available():
			return False
	except Exception:
		return False
	_ = Session
	return True


def _is_context_window_error(exc: Exception) -> bool:
	if isinstance(exc, ContextWindowError):
		return True
	name = exc.__class__.__name__.lower()
	message = str(exc).lower()
	if "contextwindow" in name or "contextwindow" in message:
		return True
	if "context window" in message or "context length" in message:
		return True
	if "context window size" in message or "context length exceeded" in message:
		return True
	return False


def total_ram_bytes() -> int:
	"""
	Estimate total system memory.
	"""
	pages = 0
	page_size = 0
	if hasattr(os, "sysconf"):
		if "SC_PHYS_PAGES" in os.sysconf_names:
			pages = int(os.sysconf("SC_PHYS_PAGES"))
		if "SC_PAGE_SIZE" in os.sysconf_names:
			page_size = int(os.sysconf("SC_PAGE_SIZE"))
	if pages and page_size:
		value = pages * page_size
		return value
	return 0


def get_vram_size_in_gb() -> int | None:
	"""
	Detect VRAM or unified memory size in GB.
	"""
	try:
		arch = subprocess.check_output(["uname", "-m"], text=True).strip()
		is_apple_silicon = arch.startswith("arm64")
		if is_apple_silicon:
			hardware_info = subprocess.check_output(
				["system_profiler", "SPHardwareDataType"], text=True
			)
			match = re.search(r"Memory:\\s(\\d+)\\s?GB", hardware_info)
			if match:
				return int(match.group(1))
		else:
			display_info = subprocess.check_output(
				["system_profiler", "SPDisplaysDataType"], text=True
			)
			vram_match = re.search(r"VRAM.*?: (\\d+)\\s?MB", display_info)
			if vram_match:
				vram_mb = int(vram_match.group(1))
				return vram_mb // 1024
	except Exception:
		return None
	return None


def choose_model(model_override: str | None) -> str:
	"""
	Pick an Ollama model based on RAM or override.
	"""
	if model_override:
		return model_override
	vram_gb = get_vram_size_in_gb()
	if vram_gb is not None:
		if vram_gb > 30:
			return "gpt-oss:20b"
		if vram_gb > 14:
			return "phi4:14b-q4_K_M"
		if vram_gb > 4:
			return "llama3.2:3b-instruct-q5_K_M"
		return "llama3.2:1b-instruct-q4_K_M"
	ram = total_ram_bytes()
	if ram and ram > 30 * 1024 * 1024 * 1024:
		return "gpt-oss:20b"
	if ram and ram > 14 * 1024 * 1024 * 1024:
		return "phi4:14b-q4_K_M"
	if ram and ram > 4 * 1024 * 1024 * 1024:
		return "llama3.2:3b-instruct-q5_K_M"
	return "llama3.2:1b-instruct-q4_K_M"


def pick_category(extension: str) -> str:
	"""
	Choose simple category from extension (broad buckets).
	"""
	ext = extension.lower()
	if ext in {"pdf", "doc", "docx", "odt", "rtf", "pages", "txt", "md", "html", "htm"}:
		return "Document"
	if ext in {"ppt", "pptx", "odp"}:
		return "Presentation"
	if ext in {"xls", "xlsx", "ods", "csv", "tsv"}:
		return "Data"
	if ext in {"png", "jpg", "jpeg", "heic", "gif", "tif", "tiff", "bmp", "svg", "svgz", "odg"}:
		return "Image"
	if ext in {"mp3", "wav", "flac", "aiff", "ogg"}:
		return "Audio"
	if ext in {"mp4", "mov", "mkv", "webm", "avi"}:
		return "Video"
	if ext in {"py", "m", "cpp", "js", "sh", "pl", "rb", "php"}:
		return "Code"
	return "Other"


def _is_guardrail_error(exc: Exception) -> bool:
	if isinstance(exc, GuardrailRefusalError):
		return True
	if _GUARDRAIL_ERRORS and isinstance(exc, _GUARDRAIL_ERRORS):
		return True
	name = exc.__class__.__name__.lower()
	if "guardrail" in name:
		return True
	msg = str(exc).lower()
	return "guardrail" in msg and "unsafe" in msg
