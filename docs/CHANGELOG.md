## 2026-02-22

### Added
- Patch 1: `fetch_github_data.py` added to collect weekly repo, commit, issue, and pull-request
  records into `out/github_data.jsonl`.
- Patch 2: `outline_github_data.py` added to parse JSONL and emit `out/outline.json` plus
  `out/outline.txt`.
- Patch 3: `outline_to_blog_post.py`, `outline_to_bluesky_post.py`, and
  `outline_to_podcast_script.py` added to produce channel outputs with hard limits.
- Patch 4: `script_to_audio.py` added for multi-speaker TTS synthesis from
  `out/podcast_script.txt`.
- Patch 5: `pipeline_text_utils.py` added for shared deterministic word/character limit logic.
- Patch 6: `tests/test_content_pipeline_limits.py` and `tests/test_outline_parser.py` added for
  parser and output-limit coverage.
- Root `Brewfile` added for macOS system dependencies used by pipeline + local LLM runtime.
- `pipeline/script_to_audio_say.py` added as a macOS `say` backend for single-speaker audio output
  with explicit progress logging, settings support, and voice listing.
- `tests/test_script_to_audio_say.py` added for `say` voice parsing and narration helper coverage.
- `automation/run_local_pipeline.py` added as the new local pipeline runner with richer terminal
  output, stage timing summary, daily-dated fetch output wiring, and per-stage retry handling.

### Updated
- `.github/workflows/weekly.yml` now runs the staged pipeline through content generation.
- `README.md` now documents implemented stage commands and output files.
- `fetch_github_data.py` now supports exclusive window presets with default `--last-day`, fetches
  `docs/CHANGELOG.md` for relevant repos, and writes one daily cache JSONL per day in the active
  window.
- `.github/workflows/weekly.yml` now calls `fetch_github_data.py --last-week` and writes daily
  cache files under `out/daily_cache`.
- `README.md` now documents preset window flags, changelog records, and daily cache behavior.
- Pipeline files are now organized under `pipeline/` and local scheduling scripts under
  `automation/` to reduce repo-root clutter.
- `pipeline/outline_github_data.py` now writes per-repo outline shards (JSON+TXT) plus
  `out/outline_repos/index.json` for LLM-friendly repo-by-repo summarization.
- `pipeline/outline_github_data.py` now uses `local-llm-wrapper` for true LLM summarization
  (`llm_repo_outline` and `llm_global_outline`) with transport/model/token controls.
- `pipeline/outline_github_data.py` now requires LLM summarization for all runs; deterministic-only
  mode flag was removed.
- `README.md` now documents local `launchd` helper scripts in `automation/`.
- `pip_requirements.txt` now reflects pipeline runtime dependencies and documents local-llm-wrapper
  runtime expectations.
- `pip_requirements.txt` now requires `apple-foundation-models` for Apple transport support.
- `pip_requirements.txt` now requires `pyyaml` for YAML settings loading.
- `README.md` local setup now installs from `pip_requirements.txt` and documents
  `brew bundle --file Brewfile`.
- `automation/run_local_pipeline.sh` setup hint now references `pip_requirements.txt`.
- Added root `settings.yaml` for `github.username` and LLM preferences
  (`transport`, `model`, `max_tokens`, `repo_limit`).
- `pipeline/fetch_github_data.py` now accepts `--settings`, reads default user from
  `settings.yaml`, and keeps `--user` as an override.
- `pipeline/fetch_github_data.py` was migrated from direct `requests` calls to a PyGithub adapter
  (`pipeline/github_client.py`) while preserving JSONL record schema and existing CLI flags.
- `pipeline/fetch_github_data.py` now serializes PyGithub repo/commit/issue objects back into
  REST-like dict payloads so downstream JSONL consumers keep the same record keys.
- `pipeline/fetch_github_data.py` now applies deterministic rate-limit handling through
  `GitHubClient.maybe_wait_for_rate_limit()` and stops cleanly on 403 rate-limit failures.
- `pip_requirements.txt` now includes `PyGithub`.
- `pipeline/outline_github_data.py` now accepts `--settings` and reads default LLM transport,
  model, max tokens, and repo limit from `settings.yaml` with CLI overrides.
- `pipeline/outline_github_data.py`, `pipeline/outline_to_blog_post.py`,
  `pipeline/outline_to_bluesky_post.py`, `pipeline/outline_to_podcast_script.py`, and
  `pipeline/script_to_audio.py` now emit explicit timestamped progress logs for each major stage.
- `automation/run_local_pipeline.sh`, `automation/install_launchd_pipeline.sh`, and
  `automation/uninstall_launchd_pipeline.sh` now emit explicit timestamped progress logs per step.
- Progress log prefix format was simplified across Python and shell scripts from full ISO timestamps
  to `HH:MM:SS` only (example: `[fetch_github_data 02:54:44]`) for cleaner local readability.
- `automation/run_local_pipeline.sh` now passes `--settings settings.yaml` for fetch and outline.
- `README.md` now documents settings-driven configuration and CLI override behavior.
- Added `pipeline/pipeline_settings.py` and `tests/test_pipeline_settings.py`.
- `pipeline/fetch_github_data.py` now logs step-by-step progress and request phases so local runs
  show current work in real time.
- `pipeline/fetch_github_data.py` now handles GitHub API 403 rate-limit responses cleanly with an
  actionable message and writes partial output instead of crashing with a raw traceback.
- `pipeline/fetch_github_data.py` now skips detail API calls for stale repos outside the active
  window by using repo `updated_at` recency checks, which reduces unauthenticated rate-limit hits.
- `settings.yaml` LLM configuration now supports multiple providers with explicit `enabled` flags
  under `llm.providers`, with Apple set as the active local provider.
- `settings.yaml` now treats Apple as model-less (`llm.providers.apple` has no `model` field).
- Ollama model selection now uses `llm.providers.ollama.models` as a list with per-model
  `enabled` flags.
- `pipeline/pipeline_settings.py` now includes shared helpers for boolean settings parsing and
  enabled-provider resolution (`get_enabled_llm_transport`, `get_llm_provider_model`).
- `pipeline/pipeline_settings.py` now enforces exactly one enabled Ollama model when Ollama is
  the active provider, raising clear errors for none or multiple enabled models.
- `pipeline/outline_github_data.py` now resolves default LLM transport/model from enabled
  provider settings and raises an error when more than one provider is enabled.
- `README.md` now documents provider names (`apple`, `ollama`) and the single-enabled-provider
  requirement.
- `tests/test_pipeline_settings.py` now covers enabled-provider selection, multi-enabled error
  handling, provider-model precedence, and legacy fallback behavior.
- `pipeline/fetch_github_data.py` CLI was minimized: removed `--api-base` and `--token`, and
  replaced `--window-days`/preset flags with a single `--last-days N` option.
- `pipeline/fetch_github_data.py` authentication now reads optional token from
  `settings.yaml` (`github.token`) instead of CLI/env-token fallbacks.
- `settings.yaml` now includes `github.token` for optional authenticated PyGithub access.
- `automation/run_local_pipeline.sh` now calls fetch with `--last-days 7`.
- `README.md` now documents `--last-days N` and settings-based token configuration.
- `pipeline/github_client.py` rate-limit messaging now references `settings.yaml` token setup.
- `pip_requirements.txt` no longer includes `requests` after PyGithub migration.
- `README.md` now documents both audio paths: multi-speaker Qwen (`script_to_audio.py`) and
  single-speaker macOS `say` (`script_to_audio_say.py`).
- `settings.yaml` now includes `tts.say.voice` and `tts.say.rate_wpm` defaults.
- `pipeline/fetch_github_data.py` window flags were adjusted to presets:
  `--last-day` (default), `--last-week`, and `--last-month`; `--last-days` was removed.
- `automation/run_local_pipeline.sh` now uses `--last-week` for fetch stage execution.
- `README.md` fetch examples and notes now document preset window flags instead of `--last-days`.
- `tests/test_fetch_github_data_features.py` now validates preset-window resolution logic.
- `pipeline/github_client.py` rate-limit handling now supports multiple PyGithub response shapes
  (`overview.core`, `overview.resources.core`, and `overview.resources["core"]`) to avoid crashes.
- `pipeline/github_client.py` now treats unknown rate-limit metadata as non-fatal for proactive
  wait checks, while still surfacing clear 403 limit errors when requests are actually blocked.
- `tests/test_github_client_rate_limit.py` now validates rate-limit parsing compatibility and
  unknown-shape safety behavior.
- `pipeline/outline_github_data.py` now supports resume caching with `--continue`/`--no-continue`
  (default continue on), reusing existing per-repo shard outlines when user/window metadata match.
- `pipeline/outline_github_data.py` now logs cache hit counts and tracks
  `llm_cached_repo_outline_count` plus `llm_generated_repo_outline_count` in outline output.
- `README.md` now documents default continue behavior and `--no-continue` override for forced
  outline regeneration.
- `tests/test_outline_parser.py` now covers repo-shard cache loading and cache-aware summarize flow.
- `pipeline/outline_to_blog_post.py` now generates blog content with `local-llm-wrapper` instead of
  deterministic paragraph stitching.
- `pipeline/outline_to_blog_post.py` now writes Markdown output by default (`out/blog_post.md`)
  suitable for MkDocs Material usage.
- `pipeline/outline_to_blog_post.py` word handling now treats `--word-limit` as a target and logs
  over-target output rather than failing hard.
- `README.md` output list and process description now refer to Markdown blog output.
- `tests/test_outline_to_blog_post.py` added for blog prompt and retry behavior.
- `tests/test_content_pipeline_limits.py` blog coverage now targets Markdown trim helper behavior.
- Shared utility modules were moved under `pipeline/podlib/`:
  - `pipeline/podlib/github_client.py`
  - `pipeline/podlib/pipeline_settings.py`
  - `pipeline/podlib/pipeline_text_utils.py`
- Pipeline scripts and related tests now import utility modules from `podlib` paths.
- `local-llm-wrapper` is now treated as first-party code in repo hygiene checks:
  `test_bandit_security`, `test_import_dot`, and `test_init_files` now scan it directly.
- `local-llm-wrapper/local_llm_wrapper` imports were migrated from relative imports to absolute
  package imports (`local_llm_wrapper.*`) to satisfy import-dot policy.
- `local-llm-wrapper/local_llm_wrapper/transports/__init__.py` was simplified to satisfy
  `__init__.py` policy checks (no import/export implementation logic).
- `local-llm-wrapper/llm_chat.py`, `local-llm-wrapper/llm_generate.py`, and
  `local-llm-wrapper/llm_xml_demo.py` now import `OllamaTransport` from
  `local_llm_wrapper.transports.ollama` instead of relying on package-level re-exports.
- `local-llm-wrapper/local_llm_wrapper/transports/ollama.py` now validates the endpoint scheme/host
  and annotates validated `urlopen` calls to satisfy Bandit B310 checks.
- `tests/test_import_requirements.py` now maps `applefoundationmodels` to
  `apple-foundation-models` via import alias normalization for dependency-policy compliance.
- `pipeline/outline_to_blog_post.py` now stamps blog output filenames with local date only
  (`YYYY-MM-DD`) and excludes time values in filenames.
- `pipeline/outline_to_blog_post.py` now auto-suffixes output filenames with date when no date is
  present, while preserving pre-dated output names.
- `README.md` output artifact naming now documents date-stamped Markdown blog filenames.
- `tests/test_outline_to_blog_post.py` now covers date-stamp filename insertion and no-duplicate
  behavior.
- `pipeline/outline_to_blog_post.py` prompt now targets daily narrative blog style and explicitly
  blocks generic writing-advice/CTA phrasing (for example comment prompts).
- `pipeline/outline_to_blog_post.py` now excludes `llm_global_outline` from blog context to reduce
  deterministic outline-like outputs.
- `pipeline/outline_to_blog_post.py` now performs blog quality validation for structural/errors
  (H1 presence and error-payload detection), while keeping `--word-limit` as a target rather than
  a strict minimum requirement.
- `pipeline/outline_to_blog_post.py` now applies salvage-first Markdown normalization:
  leading `##` is promoted to `#`, and missing top-level titles get a default H1, so usable LLM
  output is preserved instead of rejected for format drift.
- `pipeline/outline_to_blog_post.py` blog generation flow now follows repo-by-repo incremental
  drafts using `max(100, ceil((2*word_limit)/(N-1)))`, selects the single best repo draft, then
  runs a final LLM trim pass targeting `word_limit`.
- `pipeline/outline_to_bluesky_post.py` now uses `local-llm-wrapper` with the same incremental
  repo-draft workflow (per-repo draft, best-draft selection, final trim pass) using
  Bluesky-specific prompts and publish-safe final char trim.
- `pipeline/outline_to_podcast_script.py` now uses `local-llm-wrapper` with the same incremental
  repo-draft workflow (per-repo draft, best-draft selection, final trim pass) using
  N-speaker podcast-specific prompts and speaker-line salvage.
- `pipeline/outline_to_blog_post.py` progress logs now show stage-level generation steps
  (repo draft i/N, best-draft selection, final trim), plus configured LLM execution path.
- `pipeline/outline_to_bluesky_post.py` and `pipeline/outline_to_podcast_script.py` now log
  stage-level generation steps and configured LLM execution path.
- Added `pipeline/podlib/outline_llm.py` to centralize shared local-llm-wrapper setup helpers
  (`create_llm_client`, execution-path description, incremental-target formula).
- Added `pipeline/podlib/outline_draft_cache.py` for reusable per-repo intermediate draft cache
  helpers used by outline content stages.
- `pipeline/outline_to_blog_post.py`, `pipeline/outline_to_bluesky_post.py`, and
  `pipeline/outline_to_podcast_script.py` now support per-repo draft caching with
  `--continue`/`--no-continue` (default continue) and `--repo-draft-cache-dir`.
- `pipeline/outline_to_blog_post.py` now exits cleanly with progress logs when blog generation
  fails, instead of printing a traceback.
- `automation/run_local_pipeline.sh` now follows repo runtime conventions from
  `AGENTS.md`/`docs/REPO_STYLE.md`: repo root is resolved with `git rev-parse --show-toplevel`,
  `source_me.sh` is required, stage commands run via `python3` after sourcing, fetch defaults to
  `--last-day`, and blog output target path now uses Markdown (`out/blog_post.md`).
- `automation/install_launchd_pipeline.sh` now points launchd to
  `automation/run_local_pipeline.py` and executes it with `python3`.
- `README.md` local launchd runner references now point to `automation/run_local_pipeline.py`.
- `pip_requirements.txt` now includes `rich` for colored local pipeline runner output.
- `pipeline/fetch_github_data.py` main output JSONL path is now local-date-stamped by default,
  producing one top-level fetch file per day (for example `out/github_data_YYYY-MM-DD.jsonl`).
- `pipeline/podlib/github_client.py` now applies small request jitter
  (`time.sleep(random.random())`) before GitHub API calls and retries once after 403 responses by
  waiting 10 seconds, to better tolerate transient API throttling.
- `tests/test_outline_to_blog_post.py` now includes coverage ensuring short valid Markdown is still
  accepted by blog quality checks.
- `tests/test_outline_to_blog_post.py` now covers H1 salvage behavior for H2-leading and plain-text
  openings.
- Added `tests/test_outline_to_bluesky_post.py` and `tests/test_outline_to_podcast_script.py` for
  LLM orchestration coverage in non-blog outline stages.

### Validation
- `python3 -m py_compile fetch_github_data.py outline_github_data.py outline_to_blog_post.py`
- `python3 -m py_compile outline_to_bluesky_post.py outline_to_podcast_script.py script_to_audio.py`
- `python3 -m py_compile pipeline_text_utils.py tests/test_outline_parser.py tests/test_content_pipeline_limits.py`
- `.venv/bin/python -m pytest -q tests/test_outline_parser.py tests/test_content_pipeline_limits.py` (pass: `5 passed`)
- `.venv/bin/python fetch_github_data.py --help`
- `.venv/bin/python fetch_github_data.py --user vosslab --window-days 7 --max-repos 1 --output out/smoke_github_data.jsonl`
- `.venv/bin/python outline_github_data.py --input out/smoke_github_data.jsonl --outline-json out/smoke_outline.json --outline-txt out/smoke_outline.txt`
- `.venv/bin/python outline_to_blog_post.py --input out/smoke_outline.json --output out/smoke_blog_post.html --word-limit 500`
- `.venv/bin/python outline_to_bluesky_post.py --input out/smoke_outline.json --output out/smoke_bluesky_post.txt --char-limit 140`
- `.venv/bin/python outline_to_podcast_script.py --input out/smoke_outline.json --output out/smoke_podcast_script.txt --num-speakers 3 --word-limit 500`
- `.venv/bin/python -m py_compile fetch_github_data.py tests/test_fetch_github_data_features.py`
- `.venv/bin/python -m pytest -q tests/test_fetch_github_data_features.py` (pass: `4 passed`)
- `.venv/bin/python fetch_github_data.py --user vosslab --last-week --max-repos 1 --output out/smoke_github_data.jsonl --daily-cache-dir out/smoke_daily_cache`
- `.venv/bin/python -m py_compile pipeline/outline_github_data.py tests/test_outline_parser.py`
- `.venv/bin/python -m pytest -q tests/test_outline_parser.py` (pass: `3 passed`)
- `.venv/bin/python pipeline/outline_github_data.py --input out/smoke_github_data.jsonl --outline-json out/smoke_outline3.json --outline-txt out/smoke_outline3.txt --repo-shards-dir out/smoke_outline_repos`
- `.venv/bin/python -m py_compile pipeline/fetch_github_data.py pipeline/outline_github_data.py pipeline/outline_to_blog_post.py pipeline/outline_to_bluesky_post.py pipeline/outline_to_podcast_script.py pipeline/script_to_audio.py pipeline/pipeline_text_utils.py tests/test_outline_parser.py tests/test_content_pipeline_limits.py tests/test_fetch_github_data_features.py`
- `.venv/bin/python -m pytest -q tests/test_outline_parser.py tests/test_content_pipeline_limits.py tests/test_fetch_github_data_features.py` (pass: `9 passed`)
- `.venv/bin/python -m py_compile pipeline/outline_github_data.py tests/test_outline_parser.py`
- `.venv/bin/python -m pytest -q tests/test_outline_parser.py` (pass: `4 passed`)
- `.venv/bin/python pipeline/outline_github_data.py --help` (verified `--disable-llm` removed)
- `python3 tests/check_ascii_compliance.py -i pip_requirements.txt`
- `python3 tests/check_ascii_compliance.py -i Brewfile`
- `python3 tests/check_ascii_compliance.py -i README.md`
- `source source_me.sh && PYTHONPYCACHEPREFIX=/tmp/vosslab_podcast_pycache python3.12 -m py_compile pipeline/pipeline_settings.py pipeline/fetch_github_data.py pipeline/outline_github_data.py tests/test_pipeline_settings.py`
- `source source_me.sh && PYTHONPYCACHEPREFIX=/tmp/vosslab_podcast_pycache python3.12 -m pytest -q tests/test_pipeline_settings.py tests/test_fetch_github_data_features.py tests/test_outline_parser.py` (pass: `11 passed`)
- `source source_me.sh && PYTHONPYCACHEPREFIX=/tmp/vosslab_podcast_pycache python3.12 -m py_compile pipeline/github_client.py pipeline/fetch_github_data.py`
- `source source_me.sh && PYTHONPYCACHEPREFIX=/tmp/vosslab_podcast_pycache python3.12 -m pytest -q tests/test_fetch_github_data_features.py tests/test_pipeline_settings.py` (pass: `7 passed`)
- `source source_me.sh && PYTHONPYCACHEPREFIX=/tmp/vosslab_podcast_pycache python3.12 -m py_compile pipeline/outline_github_data.py pipeline/outline_to_blog_post.py pipeline/outline_to_bluesky_post.py pipeline/outline_to_podcast_script.py pipeline/script_to_audio.py`
- `source source_me.sh && PYTHONPYCACHEPREFIX=/tmp/vosslab_podcast_pycache python3.12 -m pytest -q tests/test_outline_parser.py tests/test_content_pipeline_limits.py` (pass: `7 passed`)
- `bash -n automation/run_local_pipeline.sh automation/install_launchd_pipeline.sh automation/uninstall_launchd_pipeline.sh`
- `source source_me.sh && PYTHONPYCACHEPREFIX=/tmp/vosslab_podcast_pycache python3.12 -m py_compile pipeline/fetch_github_data.py pipeline/outline_github_data.py pipeline/outline_to_blog_post.py pipeline/outline_to_bluesky_post.py pipeline/outline_to_podcast_script.py pipeline/script_to_audio.py`
- `source source_me.sh && PYTHONPYCACHEPREFIX=/tmp/vosslab_podcast_pycache python3.12 -m py_compile pipeline/fetch_github_data.py pipeline/github_client.py tests/test_fetch_github_data_features.py`
- `source source_me.sh && PYTHONPYCACHEPREFIX=/tmp/vosslab_podcast_pycache python3.12 -m pytest -q tests/test_fetch_github_data_features.py tests/test_pipeline_settings.py tests/test_outline_parser.py tests/test_content_pipeline_limits.py` (pass: `15 passed`)
- `source source_me.sh && python3.12 pipeline/fetch_github_data.py --help`
- `source source_me.sh && PYTHONPYCACHEPREFIX=/tmp/vosslab_podcast_pycache python3.12 -m py_compile pipeline/pipeline_settings.py pipeline/outline_github_data.py tests/test_pipeline_settings.py`
- `source source_me.sh && PYTHONPYCACHEPREFIX=/tmp/vosslab_podcast_pycache python3.12 -m pytest -q tests/test_pipeline_settings.py tests/test_outline_parser.py tests/test_content_pipeline_limits.py tests/test_fetch_github_data_features.py` (pass: `19 passed`)
- `source source_me.sh && python3.12 pipeline/outline_github_data.py --help`
- `source source_me.sh && PYTHONPYCACHEPREFIX=/tmp/vosslab_podcast_pycache python3.12 -m py_compile pipeline/pipeline_settings.py tests/test_pipeline_settings.py pipeline/outline_github_data.py`
- `source source_me.sh && PYTHONPYCACHEPREFIX=/tmp/vosslab_podcast_pycache python3.12 -m pytest -q tests/test_pipeline_settings.py tests/test_outline_parser.py tests/test_content_pipeline_limits.py tests/test_fetch_github_data_features.py` (pass: `22 passed`)
- `source source_me.sh && PYTHONPYCACHEPREFIX=/tmp/vosslab_podcast_pycache python3.12 -m py_compile pipeline/script_to_audio_say.py tests/test_script_to_audio_say.py`
- `source source_me.sh && PYTHONPYCACHEPREFIX=/tmp/vosslab_podcast_pycache python3.12 -m pytest -q tests/test_script_to_audio_say.py`
- `python3.12 -m py_compile pipeline/fetch_github_data.py tests/test_fetch_github_data_features.py`
- `python3.12 -m pytest -q tests/test_fetch_github_data_features.py` (pass: `5 passed`)
- `python3.12 pipeline/fetch_github_data.py --help`
- `python3.12 -m py_compile pipeline/github_client.py tests/test_github_client_rate_limit.py`
- `python3.12 -m pytest -q tests/test_github_client_rate_limit.py tests/test_fetch_github_data_features.py` (pass: `9 passed`)
- `python3.12 pipeline/fetch_github_data.py --last-day --max-repos 1 --output out/smoke_github_data.jsonl --daily-cache-dir out/smoke_daily_cache`
- `python3.12 -m py_compile pipeline/outline_github_data.py tests/test_outline_parser.py`
- `python3.12 -m pytest -q tests/test_outline_parser.py`
- `python3.12 -m py_compile pipeline/outline_to_blog_post.py tests/test_content_pipeline_limits.py tests/test_outline_to_blog_post.py`
- `python3.12 -m pytest -q tests/test_content_pipeline_limits.py tests/test_outline_to_blog_post.py` (pass: `5 passed`)
- `python3.12 pipeline/outline_to_blog_post.py --help`
- `python3.12 -m py_compile pipeline/fetch_github_data.py pipeline/outline_github_data.py pipeline/outline_to_blog_post.py pipeline/outline_to_bluesky_post.py pipeline/outline_to_podcast_script.py pipeline/script_to_audio_say.py tests/test_pipeline_settings.py tests/test_github_client_rate_limit.py tests/test_content_pipeline_limits.py tests/test_outline_to_blog_post.py`
- `python3.12 -m pytest -q tests/test_pipeline_settings.py tests/test_github_client_rate_limit.py tests/test_content_pipeline_limits.py tests/test_outline_to_blog_post.py` (pass: `19 passed`)
- `python3.12 pipeline/fetch_github_data.py --help && python3.12 pipeline/outline_to_blog_post.py --help`
- `python3.12 -m pytest -q tests/test_bandit_security.py tests/test_import_dot.py tests/test_import_requirements.py tests/test_init_files.py` (pass: `52 passed`)
- `python3.12 -m pytest -q tests/` (pass: `322 passed`)
- `python3.12 -m py_compile pipeline/outline_to_blog_post.py tests/test_outline_to_blog_post.py`
- `python3.12 -m pytest -q tests/test_outline_to_blog_post.py tests/test_content_pipeline_limits.py` (pass: `7 passed`)
- `python3.12 -m pytest -q tests/test_outline_to_blog_post.py tests/test_content_pipeline_limits.py` (pass: `8 passed`)
- `python3.12 -m py_compile pipeline/outline_to_blog_post.py`
- `python3.12 pipeline/outline_to_blog_post.py` (clean failure path validated when Apple transport fails)
