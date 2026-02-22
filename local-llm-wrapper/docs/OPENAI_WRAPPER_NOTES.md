# OpenAI wrapper notes

## Overview
- This note summarizes `simple-llm-openai-wrapper`, an API-backed wrapper kept as a sibling repo.
- The implementation lives under `simple-llm-openai-wrapper/openai_wrapper/` and provides a single class, `OpenAIWrapper`.

## Core behaviors
- Per-model configuration is driven by a config dict with global defaults and model-level overrides.
- Model fallback iterates through the model list until a call succeeds.
- Retries wrap both the API call and post-processing using tenacity and apply to each model before fallback.
- Post-processing can remove `<think>...</think>` sections and repair JSON output.
- The wrapper exposes both chat and completion flows with a shared configuration interface.

## Configuration model
- Required: a non-empty `models` list and a global `api_key`.
- Optional per-model overrides: `api_key`, `base_url`, `json_only`, `remove_thinking_sections`, `default_params`.
- Global defaults: `base_url`, `json_only`, `remove_thinking_sections`, `default_params`, and `max_attempts`.
- Per-call params merge over model defaults, which merge over global defaults.

## Error handling
- Input validation raises `ValueError` when required configuration is missing.
- Retry is triggered for OpenAI SDK errors and `ValueError`.
- If all models fail, the last exception is raised to the caller.

## Notable implementation details
- Uses the OpenAI SDK client per model config.
- `json_repair` attempts to coerce invalid JSON into valid output when enabled.
- The retry wrapper is method-level and shared by chat and completion paths.

## Ideas to consider for the local wrapper
- Per-transport default parameter merging with per-call overrides.
- Retrying post-processing steps, not just the transport call itself.
- Optional thinking-tag removal as a post-processing step.
