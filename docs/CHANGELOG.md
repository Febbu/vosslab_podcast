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
- `pipeline/outline_github_data.py` now accepts `--settings` and reads default LLM transport,
  model, max tokens, and repo limit from `settings.yaml` with CLI overrides.
- `automation/run_local_pipeline.sh` now passes `--settings settings.yaml` for fetch and outline.
- `README.md` now documents settings-driven configuration and CLI override behavior.
- Added `pipeline/pipeline_settings.py` and `tests/test_pipeline_settings.py`.

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
