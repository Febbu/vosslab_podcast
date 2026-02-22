# API implementation guide

## Overview
- This guide shows how to use `local_llm_wrapper` from the five sibling repos.
- The public surface centers on `LLMClient` plus explicit transports.
- Keep usage text-only and local-first.

## Install and import
- Depend on this repo as a local package or editable install.
- Package name: `local-llm-wrapper` (import as `local_llm_wrapper`).
- Import from `local_llm_wrapper.llm_client` for the primary entry point.

```python
from local_llm_wrapper.llm_client import LLMClient
from local_llm_wrapper.llm_utils import choose_model
from local_llm_wrapper.transports import AppleTransport, OllamaTransport
```

## Create a client
- Build transports explicitly and pass them to `LLMClient`.
- Use fallback order based on local availability.

```python
client = LLMClient(
	transports=[
		AppleTransport(),
		OllamaTransport(model=choose_model(None)),
	],
	quiet=True,
)
```

## Generate text
- Use `generate(prompt=...)` for plain text prompts.
- Use `generate(messages=...)` for chat-style inputs.
- Provide only one of `prompt` or `messages`.

```python
response = client.generate("Say hello in one sentence.", max_tokens=120)
print(response)
```

```python
messages = [
	{"role": "system", "content": "Answer in one sentence."},
	{"role": "user", "content": "What is a mutex?"},
]
print(client.generate(messages=messages, max_tokens=120))
```

## Structured helpers
- `rename` and `sort` are public and stable.
- `sort` accepts `SortItem` objects or dicts with required keys.

```python
item = {
	"path": "notes.txt",
	"name": "notes",
	"ext": "txt",
	"description": "meeting notes",
}
result = client.sort([item])
print(result.assignments)
```

## Error handling
- Catch typed errors from `local_llm_wrapper.errors`.
- Handle unavailable transports and guardrail refusals explicitly.

```python
from local_llm_wrapper.errors import GuardrailRefusalError, TransportUnavailableError

try:
	response = client.generate("Say hello.")
except GuardrailRefusalError:
	response = ""
except TransportUnavailableError as exc:
	raise RuntimeError("No local LLM available.") from exc
```

## Repo-specific guidance

### llm-file-rename-n-sort
- Keep using structured helpers, but switch to `LLMClient` instead of `LLMEngine`.
- Use `rename` and `sort` to preserve strict parsing and retries.

### automated_radio_disc_jockey
- Use `generate` with Apple-first fallback and optional instructions.
- Replace env var model selection with explicit `choose_model(None)` or override.

### biology-problems-website
- Use Ollama only, with `quiet=True`.
- Replace subprocess calls with `OllamaTransport` HTTP usage.

### screenshot-ai-renamer-macos
- Use Apple only, with short prompts and `quiet=True`.
- Keep output sanitization local to the project if needed.

### ai_image_caption
- Keep vision flow out of this wrapper.
- Use `generate` only for text-only post-processing if needed.

## Configuration rules
- Do not use custom environment variables for behavior.
- Pass explicit parameters into transports or `LLMClient`.
- Keep local-only behavior in this repo.

## Testing guidance
- Mock transports when unit testing to keep tests deterministic.
- Avoid real network or model calls inside tests.
