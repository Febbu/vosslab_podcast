# local_llm_wrapper

Local LLM wrapper with a simple, stable text-in text-out API. It supports multiple local backends (for example Ollama and Apple) via pluggable transports, with structured output helpers and robust parsing plus retry for unattended runs.

Package name: `local-llm-wrapper` (import as `local_llm_wrapper`).

## Overview
- Library-first wrapper for local text models with a small, stable API.
- Fallback across transports when a backend is unavailable.
- Structured helpers for rename/sort workflows with strict parsing and format-fix retries.

## Features
- Pluggable transports in `local_llm_wrapper/transports/`.
- Fallback chain in `LLMClient` with guardrail and context-window handling.
- Structured prompts and parsers for rename, keep, and sort workflows.
- Prompt sanitization and output normalization utilities.
- Quiet mode for non-verbose runs.
- Unified API for text prompts and chat-style message lists.

## Quick start
```python
from local_llm_wrapper.llm_client import LLMClient
from local_llm_wrapper.llm_utils import choose_model
from local_llm_wrapper.transports import AppleTransport, OllamaTransport

client = LLMClient(
	transports=[
		AppleTransport(),
		OllamaTransport(model=choose_model(None)),
	],
	quiet=True,
)

response = client.generate("Say hello in one sentence.", max_tokens=120)
print(response)
```

## Chat example
```python
from local_llm_wrapper.llm_client import LLMClient
from local_llm_wrapper.transports import OllamaTransport

client = LLMClient(transports=[OllamaTransport(model="llama3.2:3b-instruct-q5_K_M")], quiet=True)
messages = [
	{"role": "system", "content": "Answer in one sentence."},
	{"role": "user", "content": "What is a mutex?"},
]
print(client.generate(messages=messages, max_tokens=120))
```

## CLI example
```bash
/opt/homebrew/opt/python@3.12/bin/python3.12 llm_generate.py -p "Say hello in one sentence." -t 80
```

## CLI usage
`llm_generate.py` is a repo-root helper for quick prompt tests against the Ollama transport.

```bash
/opt/homebrew/opt/python@3.12/bin/python3.12 llm_generate.py --help
```

Options:
- `-p, --prompt`: Prompt text to send (default: "Say hello in one sentence.").
- `-m, --model`: Override the auto-selected model (default: auto).
- `-t, --max-tokens`: Maximum tokens to generate (default: 80).
- `-q, --quiet`: Suppress progress output (default).
- `-v, --verbose`: Show progress output.

## CLI chat demo
`llm_chat.py` is an interactive chat loop that uses chat-style messages.

```bash
/opt/homebrew/opt/python@3.12/bin/python3.12 llm_chat.py
```

Options:
- `-m, --model`: Override the auto-selected model (default: auto).
- `-s, --system`: Optional system message to start the chat.
- `-t, --max-tokens`: Maximum tokens to generate per response (default: 240).
- `-q, --quiet`: Suppress progress output (default).
- `-v, --verbose`: Show progress output.

## XML tag demo
`llm_xml_demo.py` requests a tagged response and extracts `<answer>` from the model output.

```bash
/opt/homebrew/opt/python@3.12/bin/python3.12 llm_xml_demo.py -p "Say hello in one sentence."
```

## Structured helpers
The engine includes structured helpers for common file-organization tasks.

```python
from local_llm_wrapper.llm_client import LLMClient
from local_llm_wrapper.transports import OllamaTransport

client = LLMClient(transports=[OllamaTransport(model="llama3.2:3b-instruct-q5_K_M")])
item = {
	"path": "notes.txt",
	"name": "notes",
	"ext": "txt",
	"description": "meeting notes",
}
result = client.sort([item])
print(result.assignments)
```

## Transports
- Apple: `local_llm_wrapper/transports/apple.py`.
- Ollama: `local_llm_wrapper/transports/ollama.py`.
- Protocol: `local_llm_wrapper/transports/base.py`.

## Errors
Standardized exception types live in `local_llm_wrapper/errors.py` so callers can handle guardrails, context window errors, and transport availability consistently.

## Testing
- Pytest: `/opt/homebrew/opt/python@3.12/bin/python3.12 -m pytest tests`
- Pyflakes: `tests/run_pyflakes.sh`
- ASCII compliance: `/opt/homebrew/opt/python@3.12/bin/python3.12 tests/run_ascii_compliance.py`

## Docs
- Architecture: [docs/CODE_ARCHITECTURE.md](docs/CODE_ARCHITECTURE.md)
- File layout: [docs/FILE_STRUCTURE.md](docs/FILE_STRUCTURE.md)
- Changelog: [docs/CHANGELOG.md](docs/CHANGELOG.md)

## Notes
- This repo is text-only; image or OCR workflows belong elsewhere.
- Configuration is explicit through arguments or config objects, not custom environment variables.
