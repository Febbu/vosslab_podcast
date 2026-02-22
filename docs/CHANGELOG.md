## 2026-02-22

### Additions and New Features
- Added `pipeline/summarize_changelog_data.py` as a new pipeline stage between fetch and outline.
  Reads the fetch JSONL, summarizes `repo_changelog` entries exceeding 6000 chars via
  `changelog_summarizer.summarize_long_changelog()`, and writes the updated JSONL back atomically.
  This caches the summarized output so re-running the outline stage no longer re-summarizes.
- Wired `changelog_summarize` stage into `automation/run_local_pipeline.py` between the `fetch`
  and `outline` stages.
- Added `tests/test_summarize_changelog_data.py` with 3 tests: long entry replacement via mock LLM,
  passthrough for short entries, and non-changelog record preservation.

### Behavior or Interface Changes
- Removed `summarize_bucket_changelogs()` call and `import changelog_summarizer` from
  `pipeline/github_data_to_outline.py`. The outline stage now expects already-summarized JSONL
  from the new `summarize_changelog_data` stage, eliminating repeated LLM summarization at depth 2+.
- Added `pipeline/changelog_summarizer.py` with `chunk_text()`, `summarize_changelog_chunks()`,
  `summarize_long_changelog()`, and `summarize_bucket_changelogs()`. When a changelog entry
  exceeds 6000 chars, it is split into overlapping chunks (3000 chars, 500 overlap), each chunk
  is summarized via the LLM, and the summaries are concatenated. This replaces hard truncation
  with a shorter but more complete representation of long changelogs.
- Added `pipeline/prompts/changelog_chunk_summary.txt` prompt template for changelog chunk
  summarization, instructing the LLM to keep file names, function names, commit subjects, and
  PR numbers while removing boilerplate.
- `pipeline/github_data_to_outline.py` `_generate_one_repo_draft()` now calls
  `summarize_bucket_changelogs()` before building the LLM prompt, so repos with large changelogs
  get summarized content instead of truncated text.
- Added `tests/test_changelog_summarizer.py` with 7 tests covering chunk splitting (basic, short,
  empty, overlap verification), passthrough for short text, mock LLM summarization, and in-place
  bucket mutation.
- Per-repo outline generation now uses the depth pipeline at depth 2+. At depth 1, behavior is
  unchanged (single draft). At depth 2-3, multiple drafts are generated and polished. At depth 4,
  drafts go through referee brackets before polish. Extracted `_generate_one_repo_draft()` and
  `_generate_repo_outline_with_depth()` in `pipeline/github_data_to_outline.py`.
- Added `compute_scaled_repo_targets()` to `pipeline/outline_to_blog_post.py` that computes
  per-repo blog word targets proportional to each repo's `llm_repo_outline` word count (66% scale
  factor, 100-word floor). When outlines are present, repos with richer outlines get larger blog
  targets instead of even division. Falls back to uniform targets when no outlines exist.
- `pipeline/outline_compilation.py` `merge_repo_activity()` now preserves `llm_repo_outline` on
  each repo bucket, keeping the longest outline when merging multiple days for the same repo.
- `pipeline/outline_compilation.py` `compile_outlines()` now preserves `llm_global_outline` in the
  compiled output, keeping the longest global outline across merged days.
- `pipeline/outline_to_blog_post.py` `build_repo_blog_markdown_prompt()` now includes
  `repo_outline` and `global_outline_summary` (trimmed to 1500 chars) in the prompt context when
  available, giving the LLM outline-guided emphasis for each repo draft.
- Updated `pipeline/prompts/blog_repo_markdown.txt` with instructions to use `repo_outline` as
  primary emphasis guide and `global_outline_summary` for cross-repo context.
- Added `tests/test_outline_compilation.py` with 2 tests for outline preservation through
  compilation merges.
- Added 5 tests to `tests/test_outline_to_blog_post.py` for scaled repo targets (proportional,
  normalization, empty outlines, single repo) and outline context in prompts.
- Added [docs/DESIGN_PHILOSOPHY.md](docs/DESIGN_PHILOSOPHY.md) documenting the pipeline's core
  design principles: cheap-but-mediocre local models, patience-for-quality tradeoff, caching for
  resilience, the depth system (1-4), referee pattern, and anti-hallucination guardrails.
- Added link to design philosophy doc in [README.md](README.md).
- Added `pipeline/podlib/depth_orchestrator.py` with shared depth pipeline logic: `validate_depth`,
  `compute_draft_count`, `needs_referee`, `needs_polish`, `build_referee_brackets`,
  `parse_referee_winner`, and `run_depth_pipeline`. Supports depth 1-4 with draft caching,
  referee tournament brackets, polish passes, and anti-hallucination quality-check fallback.
- Added `--depth` / `-d` flag (1-4) to all 4 LLM pipeline scripts: `blog_to_bluesky_post.py`,
  `blog_to_podcast_script.py`, `github_data_to_outline.py`, `outline_to_blog_post.py`. CLI value
  overrides `settings.yaml` default. Depth 1 preserves current single-draft behavior.
- Added `llm.depth` setting to `settings.yaml` (default 1) and `get_llm_depth()` accessor to
  `pipeline/podlib/pipeline_settings.py`.
- Added `compute_depth_draft_fingerprint()` and `build_depth_cache_path()` to
  `pipeline/podlib/outline_draft_cache.py` for depth-aware caching with depth and draft_index
  in the fingerprint to prevent cache key collisions.
- Added `--depth` passthrough to `automation/run_local_pipeline.py` for outline, blog, bluesky,
  and podcast_script stages.
- Added 8 prompt templates in `pipeline/prompts/`: 4 referee prompts (`depth_referee_blog.txt`,
  `depth_referee_outline.txt`, `depth_referee_bluesky.txt`, `depth_referee_podcast.txt`) and
  4 polish prompts (`depth_polish_blog.txt`, `depth_polish_outline.txt`,
  `depth_polish_bluesky.txt`, `depth_polish_podcast.txt`).
- Added `tests/test_depth_orchestrator.py` with pure-logic unit tests for all depth orchestrator
  functions including depth pipeline mock integration tests for depth 1, 2, and 4.
- Added `parse_all_changelog_entries()` to `pipeline/fetch_github_data.py` that extracts all
  dated changelog sections instead of only the latest one. Each `## YYYY-MM-DD` section is
  returned as a `(heading, date, entry_text)` tuple.
- Added `build_changelog_records()` to `pipeline/fetch_github_data.py` that builds one
  `repo_changelog` JSONL record per dated entry within the active fetch window, filtered by
  `day_keys`. Records are naturally bucketed into daily JSONL files.
- `pipeline/github_data_to_outline.py` now consumes `repo_changelog` records in
  `parse_jsonl_to_outline()`, populating a `changelog_entries` list on each repo bucket and
  tracking `changelog_records` in totals.
- `pipeline/prompts/outline_repo.txt` now includes a "Changelog Highlights" section so the LLM
  incorporates changelog entries when summarizing repo activity.
- Added `tests/test_fetch_changelog_data.py` with 5 tests covering multi-date parsing,
  single-date parsing, empty input, window filtering, and no-match edge cases.

### Fixes and Maintenance
- Fixed Apple Foundation Models transport (`local-llm-wrapper/local_llm_wrapper/transports/apple.py`)
  to raise `ContextWindowError` instead of generic `RuntimeError` when the prompt exceeds the
  model context window. Previously the engine's fallback logic could not detect context window
  errors from the Apple transport because the original exception was wrapped in a generic message.
- Fixed `pipeline/github_data_to_outline.py` to catch `ContextWindowError` during repo outline
  generation and retry with a trimmed changelog (6000 char budget instead of 8000). This prevents
  depth-4 runs from crashing on repos with large changelogs like bkchem (8003 changelog chars).
- `build_repo_context()` and `build_repo_llm_prompt_with_target()` in
  `pipeline/github_data_to_outline.py` now accept a `changelog_char_budget` parameter to control
  changelog truncation for context-window-constrained retries.
- Fixed changelog record `event_time` to use noon UTC (`T12:00:00+00:00`) instead of midnight
  so day-key bucketing lands on the correct date regardless of local timezone reset hour offset.
- `build_changelog_records()` now filters by UTC calendar dates the window spans (via
  `_window_utc_dates()`) instead of local-timezone `day_keys`, so changelog entries are matched
  correctly regardless of timezone offset.
- `strip_changelog_noise()` in `fetch_github_data.py` strips markdown links and backticked file
  paths from changelog text at JSONL write time. Markdown links become plain text, backticked
  paths become basenames. This reduces changelog character counts before they enter the cache.
- `_truncate_changelog_entries()` in `github_data_to_outline.py` caps changelog entries at 3
  entries and 1500 chars each to prevent context window overflow on local LLMs.
- `build_repo_context()` now includes `changelog_entries` in the repo context JSON sent to the
  LLM prompt.
- Per-repo input stats log now shows `commit_chars`, `changelog_chars`, `total_input_chars`, and
  `total_input_words` separately.

- Added `render_prompt_with_target()` to `pipeline/prompt_loader.py`. Appends a closing
  "Target N units for this document_name." line to every rendered prompt so the LLM sees the
  length constraint both near the top and as the final line before generating.
- Added `compute_repo_word_target()` to `pipeline/github_data_to_outline.py` that scales per-repo
  word targets based on input data richness (input_chars / 5 = est words, target = 50% of input
  words when under 1500). Repos with little input data get proportionally lower targets instead
  of the fixed 750-word ceiling.
- Cache word-count guardrails now use the scaled per-repo target from `compute_repo_word_target()`
  instead of the fixed ceiling target.
- Global outline log now reports total input size (chars and words) from repo summaries.

### Behavior or Interface Changes
- Context window retry for repo outlines now trims changelog to 6000 chars (25% reduction from the
  8000 default) instead of the previous 2000 chars (75% reduction).
- Repo outline log messages now show the depth value:
  `Generating repo outline 1/5: repo (target=N words, depth=D)`.
- All 12 prompt render call sites across `github_data_to_outline.py`, `outline_to_blog_post.py`,
  `blog_to_podcast_script.py`, and `blog_to_bluesky_post.py` switched from `render_prompt()` to
  `render_prompt_with_target()` for consistent closing target reminders.
- `pipeline/script_to_audio.py` now date-stamps default Qwen output to
  `podcast_audio-YYYY-MM-DD.mp3`; `pipeline/script_to_audio_say.py` now writes
  `narrator_audio-YYYY-MM-DD.mp3` by default. Runner artifact list now includes both outputs.
- Prompts now only show the target number to the LLM. Removed min/max word leaking from
  `pipeline/prompts/blog_expand.txt` and `outline_repo_targeted.txt`.
- Simplified `outline_repo_targeted.txt`: removed verbose examples and "expand every commit"
  instruction that fought the word target. Added "do not pad, paraphrase, or repeat" directive.
- Retry prompt for repo outlines now gives direction-aware feedback (too short vs too long)
  without revealing the guardrail band numbers.

### Fixes and Maintenance
- Added [docs/REPO_REVIEW-2026-02-22.md](docs/REPO_REVIEW-2026-02-22.md) with a deep-dive review
  of pipeline output quality, LLM prompt effectiveness, and prioritized recommendations.
- Added `pipeline/prompt_loader.py` with `load_prompt()` and `render_prompt()` for loading
  externalized prompt templates from `pipeline/prompts/` using `{{token}}` placeholders.
- Created 20 prompt template files in `pipeline/prompts/` covering blog, bluesky, podcast,
  outline, and speaker personality prompts. All prompts are now editable text files.
- Added `pipeline/podlib/audio_utils.py` shared audio utilities module with `parse_script_lines()`,
  `get_unique_speakers()`, `build_single_voice_narration()`, `parse_say_voices()`,
  `list_available_say_voices()`, `resolve_voice_name()`, and `convert_to_mp3()`. Both
  `script_to_audio.py` and `script_to_audio_say.py` now use this shared module.
- Added `resolve_latest_script()` to `pipeline/script_to_audio_say.py` that falls back to the
  most recent dated file (e.g. `podcast_narration-2026-02-22.txt`) when the default non-dated
  path does not exist.
- Added Q101 radio personalities (BHOST, KCOLOR, CPRODUCER) in `pipeline/prompts/bhost.txt`,
  `kcolor.txt`, `cproducer.txt`, and `show_intro.txt`.
- `pipeline/blog_to_podcast_script.py` now generates dual output: 3-speaker `podcast_script-*.txt`
  and 1-speaker `podcast_narration-*.txt` (BHOST monologue for macOS `say` TTS). Added
  `--skip-narration` flag to disable the solo narration pass.
- Added `tests/test_prompt_loader.py` with 6 tests for prompt loading and rendering.

### Behavior or Interface Changes
- Renamed `pipeline/outline_to_bluesky_post.py` to `pipeline/blog_to_bluesky_post.py` (via
  `git mv`). Bluesky stage now reads blog markdown instead of raw outline JSON, using single-pass
  LLM summarization instead of per-repo drafts.
- Renamed `pipeline/outline_to_podcast_script.py` to `pipeline/blog_to_podcast_script.py` (via
  `git mv`). Podcast stage now reads blog markdown instead of raw outline JSON.
- Replaced SPEAKER_1/SPEAKER_2/SPEAKER_3 labels with Q101 personality names BHOST/KCOLOR/CPRODUCER
  in podcast script generation.
- All prompt-building functions across `outline_to_blog_post.py`, `blog_to_bluesky_post.py`,
  `blog_to_podcast_script.py`, and `github_data_to_outline.py` now use `prompt_loader` instead
  of inline f-strings.
- Removed `repo_index` and `repo_total` from blog per-repo prompt context to stop blog posts
  from parroting "repository N of M".
- `pipeline/blog_to_bluesky_post.py` added hardened XML tag stripping regex fallback that removes
  all XML-like tags from bluesky output.
- `automation/run_local_pipeline.py` updated stage commands to use renamed pipeline files. Removed
  `--char-limit 140` override (default 280 is correct). Removed `--num-speakers` argument.
  Added `podcast_narration` to artifact list.
- `pipeline/script_to_audio_say.py` default script path changed from `out/podcast_script.txt` to
  `out/podcast_narration.txt` (1-speaker output for TTS). Outputs MP3 via `say` -> AIFF -> `lame`.
- `pipeline/script_to_audio.py` (Qwen TTS) refactored to use `podlib.audio_utils` for shared
  parsing and MP3 conversion. Outputs MP3 via WAV -> `lame`.
- Global outline target now scales with input size: `min(2000, max(400, input_words * 0.75))`
  instead of fixed 2000-word target. Prevents the LLM from padding short inputs.
- `automation/run_local_pipeline.py` added `--no-continue` flag that passes through to outline
  and blog stages to skip cached outlines and blog posts. Added `podcast_audio` stage.
- Replaced `ffmpeg` with `lame` in `Brewfile` for AIFF/WAV to MP3 conversion.
- Renamed test files: `test_outline_to_bluesky_post.py` to `test_blog_to_bluesky_post.py`,
  `test_outline_to_podcast_script.py` to `test_blog_to_podcast_script.py`. Updated imports,
  fixtures, and assertions.
- Updated `tests/test_content_pipeline_limits.py` to use blog markdown input and new module names.
- Added `prompt_loader` to `LOCAL_IMPORT_WHITELIST` in `tests/test_import_requirements.py`.

### Removals and Deprecations
- Removed per-repo draft caching, `--repo-draft-cache-dir`, `--continue`/`--no-continue` flags
  from bluesky and podcast stages (replaced by single-pass blog summarization).
- `speaker_styles.txt` content split into `pipeline/prompts/` files; original file can be deleted.

### Additions and New Features
- `pipeline/podlib/outline_llm.py` added `strip_xml_wrapper()` helper to strip common XML wrapper
  tags (`<response>`, `<output>`, `<post>`, `<blog>`, `<podcast_script>`, `<content>`) from LLM
  output, using `local_llm_wrapper.llm_utils.extract_xml_tag_content` when available.

### Behavior or Interface Changes
- `pipeline/github_data_to_outline.py` commit messages now keep the first 3 non-empty lines
  (joined with spaces) instead of only the first line, giving richer context to LLM prompts.
- `pipeline/github_data_to_outline.py` `build_repo_llm_prompt()` revised to replace speculative
  sections (Risks, Suggested Next Actions) with grounded sections (Notable Commits with verbatim
  citations, Summary of what changed) and added few-shot examples and anti-speculation guardrails.
- `pipeline/github_data_to_outline.py` `build_global_llm_prompt()` simplified from 5 sections to
  3 (Day Overview, Top Repository Highlights, Summary) with few-shot examples and anti-speculation
  guardrails.
- `pipeline/outline_to_blog_post.py` all four prompt builders now include engineer-tone guidance,
  concrete-noun rules, anti-marketing word list, and speculation guardrails. The two main prompts
  also include a few-shot example of good output style.
- `pipeline/outline_to_bluesky_post.py` `--char-limit` default changed from 140 to 280 (Bluesky
  limit is 300; 280 gives margin).
- `pipeline/outline_to_bluesky_post.py` all three prompt builders now include platform description,
  concrete-noun guidance, no-links rule, example output, and speculation guardrails.
- `pipeline/outline_to_podcast_script.py` all three prompt builders now include speaker role
  descriptions (host, technical reviewer, context provider), conversational tone guidance,
  concrete-noun rules, anti-marketing language, speculation guardrails, and a few-shot example
  exchange.
- All four content stages (`github_data_to_outline`, `outline_to_blog_post`,
  `outline_to_bluesky_post`, `outline_to_podcast_script`) now call
  `outline_llm.strip_xml_wrapper()` after every `client.generate()` to strip XML wrapper tags
  from model responses.

### Fixes and Maintenance
- `tests/test_outline_parser.py` updated to expect joined multi-line commit messages after the
  commit truncation change.

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
- `pipeline/fetch_github_data.py` now skips only the currently rate-limited repo detail stage
  (commits/issues/changelog) and continues processing subsequent repos, instead of aborting all
  remaining repo detail fetches.
- `pipeline/fetch_github_data.py` now caches `list_repos` results for 24 hours under
  `out/cache/list_repos_<user>.json`, reuses cached repo metadata on cache hit, and refreshes the
  cache on miss.
- `pipeline/fetch_github_data.py` now resolves per-repo detail fetch objects via
  `GitHubClient.get_repo(full_name)` so detail calls still work when repository lists come from
  cache.
- `tests/test_fetch_github_data_features.py` now includes repo-list cache round-trip and TTL-expiry
  coverage.
- Added `pipeline/podlib/github_cache.py` as an abstract, reusable filesystem cache for GitHub
  query payloads.
- `pipeline/podlib/github_client.py` now routes all query methods through cached query paths
  (`list_repos`, `list_commits`, `list_issues`, `get_file_content`) and tracks API usage counters
  (`api_call_count`, per-context call counts, cache hits/misses).
- `pipeline/fetch_github_data.py` now logs GitHub API usage counters at end of run.
- `pipeline/fetch_github_data.py` now supports stale repo-list cache fallback when fresh list cache
  is unavailable, so list-rate-limit windows do not block local test runs.
- `pipeline/fetch_github_data.py` repo detail collection is now commit-focused only (issues/pull
  request listing calls were removed from fetch flow).
- `tests/test_outline_to_blog_post.py` now includes coverage ensuring short valid Markdown is still
  accepted by blog quality checks.
- `tests/test_outline_to_blog_post.py` now covers H1 salvage behavior for H2-leading and plain-text
  openings.
- Added `tests/test_outline_to_bluesky_post.py` and `tests/test_outline_to_podcast_script.py` for
  LLM orchestration coverage in non-blog outline stages.
- `pipeline/outline_to_blog_post.py` prompts now explicitly require first-person singular
  narrative voice.
- `pipeline/outline_to_bluesky_post.py` now date-stamps output filenames by default
  (`bluesky_post-YYYY-MM-DD.txt`).
- `pipeline/outline_to_podcast_script.py` now date-stamps output filenames by default
  (`podcast_script-YYYY-MM-DD.txt`).
- `pipeline/github_data_to_outline.py` now renders Markdown-first daily outlines
  (`# GitHub Daily Outline`) and writes dated daily snapshots under
  `out/<user>/daily_outlines/github_outline-YYYY-MM-DD.json|md`.
- Added `pipeline/outline_compilation.py` to merge daily outlines for
  `--last-day|--last-week|--last-month`, skip empty days, and emit compiled outputs for downstream
  stages (`out/<user>/outline.json` and `compilation_outline-<window>-YYYY-MM-DD.md`).
- `automation/run_local_pipeline.py` now includes the required `outline_compilation` stage and
  prints final artifact paths at run completion.
- Default output and cache paths are now user-scoped (`out/<github.username>/...`) across fetch,
  outline, content, and audio scripts when CLI paths are not explicitly overridden.
- Added `docs/OUT_DIRECTORY_ORGANIZATION_SPEC.md` and aligned script defaults to the spec.
- `automation/install_launchd_pipeline.sh` now writes launchd logs to macOS system logs:
  `~/Library/Logs/vosslab_podcast/launchd/`.
- `pipeline/podlib/github_client.py` rate-limit messages now log reset as local clock time only
  (`reset_local=HH:MM:SS`) instead of full UTC datetime.
- `pipeline/github_data_to_outline.py` global outline generation now handles
  context-window overflow by shrinking prompt size and retrying automatically.
- `pipeline/github_data_to_outline.py` now applies long-form daily target guidance:
  global target ~2000 words with one retry when outside 1000-4000 words, and per-repo target words
  computed as `max(750, ceil(2000/(N-1)))`.
- `pipeline/github_data_to_outline.py` global-stage wording now uses daily/compilation labels
  (removed stale "weekly" wording in progress logs and LLM purpose tags).
- `automation/run_local_pipeline.py` now supports `--no-api-calls`, which skips fetch and reuses
  latest cached fetch JSONL so the rest of the pipeline can be tested without GitHub API calls.

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
- `source source_me.sh && pytest tests/` (pass: `377 passed`)
- `source source_me.sh && pytest tests/ -q` (pass: `378 passed`)
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
