# dr_voss -> main Merge Shortlist

Date: 2026-03-04
Scope: Keep `main` architecture and import only low-risk improvements from `dr_voss`.

## Base Decision
- Keep current `main` pipeline as system of record:
  - `run_daily.py`
  - `pipelines/01_logs_to_outline.py`
  - `pipelines/02_outline_to_blog.py`
  - `pipelines/03_blog_to_script.py`
  - `pipelines/04_script_to_audio.py`
- Do not merge `dr_voss` wholesale.

## Phase 1 (Safe to import now)
1. Stage retry wrapper logic
- Source reference: `dr_voss:automation/run_local_pipeline.py`
- Target: add retry options in `run_daily.py`
- Value: transient API/LLM failures become recoverable.

2. Apple TTS operational utilities
- Source reference: `dr_voss:pipeline/script_to_audio_say.py`, `dr_voss:pipeline/podlib/audio_utils.py`
- Target: improve `pipelines/04_script_to_audio.py`
- Keep:
  - voice listing helper
  - cleaner voice resolution/fallback
  - optional dated output naming
- Do not copy full `podlib` structure.

3. Minimal dependency split
- Source reference: `dr_voss:pip_requirements-dev.txt`
- Target:
  - keep runtime deps in `requirements.txt`
  - add optional dev deps file (tests/lint only)

## Phase 2 (Optional, after Phase 1 stable)
1. Changelog enrichment
- Source reference: `dr_voss:pipeline/fetch_github_data.py`, `dr_voss:pipeline/summarize_changelog_data.py`
- Target: extend step 1 data quality only.

2. Prompt-driven narration style
- Source reference: `dr_voss:pipeline/prompts/`
- Target: optional style layer for step 3.
- Constraint: keep deterministic fallback when LLM unavailable.

## Not Recommended to merge now
- `local-llm-wrapper/` vendored tree
- `depth_orchestrator` multi-pass generation system
- Full `pipeline/` replacement from `dr_voss`
- Replacing `data/YYYY-MM-DD` contract

## Integration order
1. Add retry support to `run_daily.py`.
2. Refine Apple TTS behavior in `pipelines/04_script_to_audio.py`.
3. Add targeted tests for step runner + script/audio interfaces.
4. Re-run end-to-end for one active day with:
   - `--audio-engine qwen`
   - `--audio-engine apple`

## Acceptance criteria for Phase 1
- Same command surface remains valid:
  - `python3 run_daily.py --date YYYY-MM-DD --audio-engine qwen --mp3`
- Pipeline remains deterministic without LLM wrapper.
- Failures in one stage can retry and continue only when successful.
- No directory layout changes required for current users.
