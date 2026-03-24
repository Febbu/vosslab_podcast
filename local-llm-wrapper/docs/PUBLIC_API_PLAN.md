# Public API plan

## Overview
- This document plans the public API for the local LLM wrapper.
- The plan uses ideas from [docs/OPENAI_WRAPPER_NOTES.md](docs/OPENAI_WRAPPER_NOTES.md) while staying local only.
- The API is shaped around the five sibling repos summarized in [docs/LLM_WRAPPER_IDEAS.md](docs/LLM_WRAPPER_IDEAS.md).

## Proposed public surface
- `LLMClient` as the main entry point with a stable constructor.
- `generate(prompt=..., messages=..., purpose=..., max_tokens=...) -> str` for text or chat inputs.
- `rename(current_name, metadata) -> RenameResult` for filename generation.
- `sort(items) -> SortResult` for category assignment.
- `AppleTransport(...)` and `OllamaTransport(...)` as the supported backends.
- Helpers: `choose_model(...)`, `apple_models_available(...)`, and `sanitize_filename(...)`.
- Errors: `LLMError`, `TransportUnavailableError`, `GuardrailRefusalError`, `ContextWindowError`.

## Public exports (initial)
- Core: `LLMClient`, `AppleTransport`, `OllamaTransport`.
- Helpers: `choose_model`, `apple_models_available`, `sanitize_filename`.
- Structured: `rename`, `sort`, `RenameResult`, `SortResult`.
- Errors: `LLMError`, `TransportUnavailableError`, `GuardrailRefusalError`, `ContextWindowError`.

## Package mapping
- `llm-file-rename-n-sort` uses `rename`, `sort`, and `keep_action`.
- `automated_radio_disc_jockey` uses `generate` with fallback transports and instructions.
- `biology-problems-website` uses `generate` with `quiet=True` and Ollama only.
- `screenshot-ai-renamer-macos` uses `generate` with Apple only and short outputs.
- `ai_image_caption` stays out of scope but can use `generate` for text-only post-processing.

## Justification
- A single entry point keeps the API surface small and testable.
- `generate` with prompt or messages mirrors the OpenAI wrapper without adding
  network config. See [docs/OPENAI_WRAPPER_NOTES.md](docs/OPENAI_WRAPPER_NOTES.md).
- The structured helpers keep file rename and sort flows consistent across repos.
  See [docs/LLM_WRAPPER_IDEAS.md](docs/LLM_WRAPPER_IDEAS.md).
- Explicit transports keep configuration out of environment variables per policy.
  See [docs/LLM_WRAPPER_IDEAS.md](docs/LLM_WRAPPER_IDEAS.md).

## Design decisions
- Use `LLMClient` as the public name and keep `LLMEngine` internal.
- Keep `generate` as the only text primitive with prompt or messages, not a chat alias.
- Keep `keep_action` internal until at least two repos need it.
- Keep transports public so fallback chains remain configurable and explicit.

## Scope boundaries
- Text only. No OCR, PDF parsing, or file I/O utilities inside this library.
- Local-first: local backends are required for the primary workflows.

## Public API stability rules
- Add public methods only when at least two downstream repos need them.
- Treat `LLMClient.generate` and the structured helpers as stable contracts.

## Structured output contract
- Use a single structured format for all helpers.
- Keep the same parse-retry strategy and max attempts across helpers.

## Model selection behavior
- Allow explicit model overrides on transports.
- Keep the default selection heuristic for Ollama where it is useful.
- Favor fallback chains when a model is unavailable.

## Logging and observability
- Log transport name, purpose, and retry count.
- Avoid logging prompt content by default.

## Errors and return types
- Keep `generate` returning plain text.
- Use typed result objects for structured helpers.

## Testing priorities
- Golden tests for parsing and retry behavior using saved model outputs.
- Transport tests with mocked HTTP for Ollama and stubs for Apple.

## Open questions
- Confirm the exact public exports list in `local_llm_wrapper/llm.py`.
- Confirm the canonical structured format (XML tags or JSON).
- Confirm the local-first definition for any future integrations.

## Next steps
- Update exports and docs to reflect `LLMClient` as the public surface.
- Expand README examples to match the final public API.
- Add tests for any new public aliases or helpers.
