# LLM Wrapper Analysis and Consolidation Ideas

## Overview

This document reviews the LLM-related code in five local repos to guide a unified wrapper. The focus is on backend selection, prompt/response handling, and transport design. Per `PYTHON_STYLE.md`, custom environment variables are not acceptable for configuration; use explicit config objects, CLI args, or config files instead.

**Scope:** LLM-only, text-in/text-out. No OCR, image, or document parsing inside this wrapper.

---

## Project-by-Project Analysis

### 1. ai_image_caption (Out of Scope)

**Location:** `ai_image_caption/`

**Purpose:** Image captioning with vision-language models (no text-only LLM wrapper). **Out of scope** for the unified text-only wrapper.

**Files:**
- `image_captioning.py` (ViT-GPT2)
- `moondream2.py` (Moondream2)
- `common_func.py` (MPS helpers, image resize, attention masks)

**Notes:**
- Uses **MPS-only**: `common_func.get_mps_device()` raises if MPS is unavailable.
- `setup_ai_components()` returns a dict with model/tokenizer/device/prompt.
- `moondream2.py` uses `caption()` when no prompt, `query()` when prompt provided.
- Not a text LLM wrapper, but the **component-dict pattern** is consistent with other repos.

---

### 2. automated_radio_disc_jockey

**Location:** `automated_radio_disc_jockey/`

**Purpose:** Generates DJ speech and picks songs using LLM output.

**Files:**
- `llm_wrapper.py`
- `config_apple_models.py`

**LLM wrapper behavior:**
- **Backend selection**: `get_llm_backend(preferred)` chooses `afm`, `ollama`, or `auto`.
- **Env var usage (undesired):** `DJ_LLM_BACKEND` and `OLLAMA_MODEL` are consulted.
- **Ollama** via subprocess: `ollama list`, `ollama run`.
- **Model selection** based on VRAM thresholds (40/14/4 GB).
- XML helpers: `extract_xml_tag()` and `<response>` extraction.
- Status output via `Colors`.

**Apple Foundation Models wrapper:**
- `_require_apple_intelligence()` checks arm64 + macOS 26+ + availability.
- `run_apple_model()` supports **instructions**, **retries**, and **temperature**.

---

### 3. biology-problems-website

**Location:** `biology-problems-website/`

**Purpose:** Generates concise problem-set titles.

**Files:**
- `llm_wrapper.py`
- `llm_generate_problem_set_title.py`

**LLM wrapper behavior:**
- **Ollama-only**, via subprocess `ollama run`.
- `select_ollama_model()` uses VRAM thresholds; **raises** if VRAM is unknown.
- `query_ollama_model()` supports `quiet=True` to silence status output.
- XML tag parsing is identical to the DJ wrapper.

**Usage:**
- `llm_generate_problem_set_title.py` builds a long prompt with example titles, calls `llm_wrapper`, and parses the `###` heading out of the response.

---

### 4. llm-file-rename-n-sort (Most Advanced)

**Location:** `llm-file-rename-n-sort/rename_n_sort/`

**Purpose:** Rename and categorize files with strict prompt/response handling.

**Files:**
- `llm_engine.py` (fallback engine + parse retry)
- `llm_utils.py` (hardware detection, sanitizers, logging)
- `llm_prompts.py` (dataclass request + prompt builders)
- `llm_parsers.py` (strict XML parsing)
- `transports/apple.py` and `transports/ollama.py`
- `llm.py` (compat exports)

**Key strengths:**
- **Transport abstraction**: `LLMTransport` protocol decouples backend.
- **Fallback chain**: `LLMEngine` tries transports in order.
- **Parse retry**: If output malformed, issue a format-fix prompt and retry.
- **Parse logging**: `log_parse_failure()` stores prompt/response for debugging.
- **Prompt sanitization**: `_sanitize_prompt_text()` removes noise and duplicates.
- **Output sanitization**: `sanitize_filename()` and `normalize_reason()`.

**Ollama transport:**
- **HTTP `/api/chat`** with JSON payload (not subprocess).
- Supports **conversation history** and optional system message.
- Random sleep before request to reduce burst calls.

**Apple transport:**
- Validates arm64 + macOS 26+ + AFM availability.
- Uses `Session.generate()` with `temperature=0.2`.
- **No retries or instructions** in this transport (unlike other repos).

**Model selection:**
- `choose_model(model_override)` picks by VRAM or RAM, with explicit override param (no env var).

---

### 5. screenshot-ai-renamer-macos (Out of Scope)

**Location:** `screenshot-ai-renamer-macos/`

**Purpose:** Rename macOS screenshots using OCR + caption context. **Out of scope** for the unified text-only wrapper.

**Files:**
- `tools/config_apple_models.py`
- `tools/intelligent_filename.py`
- `tools/generate_caption.py`

**LLM wrapper behavior:**
- **AFM-only** for filename generation.
- `run_apple_model()` supports **instructions**, **retries**, `max_tokens=120`.
- `_require_apple_intelligence()` mirrors the DJ wrapper.

**Prompting and post-processing:**
- `generate_intelligent_filename()` builds a rules-heavy prompt, truncates OCR/caption context, and sanitizes output into a `.png` filename.
- Output normalization: lowercasing, underscores, and character whitelist.

**Vision captioning:**
- Moondream2 or ViT-GPT2 (MPS).
- `setup_ai_components()` returns a dict with model/tokenizer/device and a `backend` key.

---

## Common Patterns Across Repos

1. **Hardware detection**  
   `get_vram_size_in_gb()` via `system_profiler` for Apple Silicon or Intel VRAM.

2. **Model selection heuristics**  
   Thresholds centered around 40/14/4 GB for Ollama.

3. **XML-like response parsing**  
   Most text LLM callers expect tagged output and parse with regex.

4. **Apple Foundation Models gating**  
   Arm64 + macOS 26+ + `apple_intelligence_available()` checks.

5. **Component dicts for vision models**  
   Vision pipelines pass `{model, tokenizer, device, prompt}`.

---

## Differences and Variations

| Feature | ai_image_caption | auto_radio_dj | biology-website | llm-file-rename | screenshot-rename |
|---|---|---|---|---|---|
| **Ollama** | No | Yes (subprocess) | Yes (subprocess) | Yes (HTTP) | No |
| **AFM** | No | Yes | No | Yes | Yes |
| **Vision Models** | Yes | No | No | No | Yes |
| **Backend fallback** | No | Yes (auto) | No | Yes (chain) | No |
| **Transport abstraction** | No | No | No | Yes | No |
| **Parse retry** | No | No | No | Yes | No |
| **Env var config** | No | Yes (undesired) | No | No | No |

---

## Env Var Policy (Required)

Per `PYTHON_STYLE.md`: no custom environment variables to configure behavior.  
Configuration must be **explicit** via CLI args, config files, or direct function parameters.

This means the unified wrapper should **not** use `DJ_LLM_BACKEND`, `OLLAMA_MODEL`, or similar env vars.

---

## Why llm-file-rename-n-sort Is the Best Foundation

1. **Transport protocol** keeps backends isolated and testable.
2. **HTTP-based Ollama** is more robust than `subprocess` calls.
3. **Fallback chain** enables Apple-first or Ollama-first policies.
4. **Strict parsing + retry** improves reliability of structured outputs.
5. **Prompt and response sanitization** reduces garbage in/out.
6. **Model selection via explicit override param**, not env vars.

**Keep most of these ideas**, but add:
- AFM **instructions + retries** (borrow from DJ + screenshot projects).
- Optional **quiet mode** (borrow from biology wrapper).

---

## Recommended Unified Wrapper Design

### Directory Structure
```
llm_wrapper/
  __init__.py
  engine.py            # LLMEngine with fallback + parse retry
  parsers.py           # strict XML-like parsers (single source of truth)
  utils.py             # model selection, sanitizers, logging
  transports/
    base.py
    ollama.py          # HTTP /api/chat
    apple.py           # AFM Session wrapper + retries
  errors.py            # standardized exception taxonomy
```

### Configuration (No Env Vars)
Use explicit params or a config file:
```python
engine = LLMEngine(
	transports=[
		AppleTransport(max_tokens=1200, instructions="..."),
		OllamaTransport(model=choose_model(None)),
	],
	quiet=False,
)
```

If a CLI is needed:
- Provide `--backend`, `--model`, `--base-url`, `--quiet` flags.
- Avoid environment variables entirely.
The wrapper should remain **library-first**; any CLI is optional and should not become the primary interface.

### Text-Only Contract
- Accepts prompt strings plus optional system text and optional schema spec.
- Reject non-text payloads (bytes, file paths, image objects) early with a clear error.
- Keep document parsing in a separate preprocessor layer that feeds text into this wrapper.

### Conversation History (Opt-In, Bounded)
- Default to stateless single-call behavior.
- If history is enabled, cap total turns (e.g., `max_turns=6`) and truncate oldest.
- Keep this logic inside the transport so it is backend-specific and testable.

### Standardized Error Taxonomy
- One exception per failure class:
  - TransportUnavailableError
  - ContextWindowError
  - GuardrailRefusalError
  - ParseError (already present)
- Make error types stable so callers can handle them cleanly.

### Rate Limiting
- Keep any `time.sleep(random.random())` in network transports (Ollama HTTP, future APIs), not in call sites.

---

## Features to Keep (from llm-file-rename-n-sort)

1. `LLMTransport` protocol and transport list.
2. `LLMEngine._generate_with_fallback()`.
3. Parse-retry + format-fix prompts.
4. `ParseError` with raw text preservation.
5. `sanitize_filename()` and `normalize_reason()`.
6. `log_parse_failure()` to audit malformed responses.

---

## Features to Borrow (from other projects)

1. **AFM session instructions + retry loop**  
   From `automated_radio_disc_jockey/config_apple_models.py` and
   `screenshot-ai-renamer-macos/tools/config_apple_models.py`.

2. **Quiet mode**  
   From `biology-problems-website/llm_wrapper.py`.

3. **Prompt discipline for structured outputs**  
   Keep the strict "return only tags" behavior and example outputs from existing prompt builders.

---

## Migration Plan (High-Level)

1. Extract the core engine + transports from `llm-file-rename-n-sort`.
2. Add AFM retry/instructions, optional quiet mode, and standardized errors.
3. Migrate the "best" repo first while keeping its public API stable, so behavior changes are debugged once.
4. Replace each repo's wrapper with the unified package:
   - `llm-file-rename-n-sort`: minimal change (already close).
   - `automated_radio_disc_jockey`: replace `llm_wrapper.py` + `config_apple_models.py`.
   - `biology-problems-website`: replace `llm_wrapper.py`.
   - `screenshot-ai-renamer-macos`: replace `tools/config_apple_models.py`.
   - `ai_image_caption`: no text LLM wrapper needed; keep vision models as-is.

---

## Bottom Line

**Yes** -- `llm-file-rename-n-sort` is the most advanced and is worth keeping as the core.  
Add AFM retries/instructions, a standardized error taxonomy, opt-in bounded history, and remove any env-var-based configuration. Keep the wrapper strictly text-only to avoid scope creep.

---

## Minimal API Surface (Suggested)

- `LLMEngine.generate(prompt: str, *, purpose: str | None = None, max_tokens: int) -> str`
- `purpose` is only for logging/debugging, not behavior.
- `LLMEngine.generate_parsed(request_obj) -> result_obj`
- `run_llm(prompt, ...)` as compatibility sugar only (legacy).
