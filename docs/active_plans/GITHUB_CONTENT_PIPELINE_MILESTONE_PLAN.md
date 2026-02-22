# GitHub Content Pipeline Milestone Plan

## Title and objective
Build a durable, script-per-stage pipeline that transforms one week of GitHub activity into four publishable outputs: JSONL archive, long-form outline, 500-word blog post, 140-character Bluesky post, and a 500-word N-speaker podcast script plus TTS audio.

## Design philosophy
- Keep one script per stage with explicit file contracts between stages.
- Prefer deterministic, testable transforms over hidden prompt/state behavior.
- Treat outputs as products with hard limits (word/character/speaker constraints) enforced by gates.
- Keep rollout additive: deliver new scripts beside legacy flow, then retire legacy after parity gates pass.

## Scope and non-goals
### Scope
- Introduce and standardize this pipeline:
  1. `fetch_github_data.py`
  2. `outline_github_data.py`
  3. `outline_to_blog_post.py`
  4. `outline_to_bluesky_post.py`
  5. `outline_to_podcast_script.py`
  6. `script_to_audio.py`
- Define stable intermediate/output paths under `out/`.
- Add verification gates for word/character limits and speaker-count conformance.
- Update docs to reflect the new pipeline and deprecation path for `fetch_and_script.py` and `tts_generate.py`.

### Non-goals
- Building publication/upload clients for website hosting or Bluesky posting.
- Expanding beyond weekly window logic.
- Adding non-GitHub data sources.
- Tuning voice quality beyond functional multi-speaker correctness.

## Current state summary
- Existing flow is monolithic: `fetch_and_script.py` writes digest + script.
- Existing TTS path is `tts_generate.py` and `voices.json`.
- README now reflects the target process flow but implementation is still legacy.
- Planning context files expected by the manager skill are missing in this repo:
  - `refactor_progress.md`
  - prior active plan docs (newly created in this effort)

## Architecture boundaries and ownership
- Data Acquisition Component: owns GitHub API fetch, pagination, auth handling, and JSONL emission.
- Outline Synthesis Component: owns parsing/aggregation from JSONL to a structured outline.
- Channel Rendering Component: owns transformations from outline into blog/bluesky/podcast text outputs.
- Audio Rendering Component: owns TTS conversion from podcast script to audio artifact.
- Verification and Contracts Component: owns schema/limit checks and gate commands across all stages.
- Documentation and Release Component: owns README, changelog notes, and closure records.

## Mapping: milestones and workstreams map to components and patches
- Milestone M1 maps to Data Acquisition Component and Verification and Contracts Component; expected patches are acquisition contract patches and fetch verification patches.
- Milestone M2 maps to Outline Synthesis Component and Verification and Contracts Component; expected patches are outline schema patches and parser verification patches.
- Milestone M3 maps to Channel Rendering Component and Verification and Contracts Component; expected patches are per-channel renderer patches and constraint-gate patches.
- Milestone M4 maps to Audio Rendering Component and Documentation and Release Component; expected patches are speaker-audio mapping patches, rollout/compatibility patches, and docs patches.

## Milestone plan (ordered, dependency-aware)
- D1: JSONL contract approved (fields, timestamps, event types, repo identity keys).
- D2: Outline contract approved (sections, ranking rules, metadata keys, deterministic ordering).
- D3: Channel constraint policy approved (blog <=500 words, bluesky <=140 chars, podcast <=500 words + N speakers).
- D4: Audio contract approved (speaker tag grammar, voice mapping, output file format, failure behavior).
- D5: Release gate checklist approved (tests, docs, migration, rollback).

1. M1: Establish acquisition contract and JSONL fetch stage
- Depends on: D1 (contract is required before implementation details)

2. M2: Establish outline stage and deterministic summarization
- Depends on: D1 (input contract), D2 (outline contract)

3. M3: Establish channel renderers and hard limit enforcement
- Depends on: D2 (outline contract), D3 (channel constraints)

4. M4: Establish multi-speaker audio stage and complete migration
- Depends on: D3 (speaker constraints), D4 (audio contract), D5 (release gate checklist)

## Workstream breakdown
### M1 workstreams
- WS1.1 Data Acquisition Core
Goal: Fetch all weekly GitHub data and write JSONL.
Owner: Coder A
Work packages: target 6-10
Interfaces: needs `GITHUB_USER`, token config; provides `out/github_data.jsonl`
Expected patches: 2-3 (fetch engine, pagination/rate-limit handling, output writer)

- WS1.2 Acquisition Contract Validation
Goal: Enforce JSONL schema and timestamp normalization.
Owner: Coder B
Work packages: target 6-8
Interfaces: needs WS1.1 sample outputs; provides schema checks and validation commands
Expected patches: 2 (schema gate, validation CLI)

- WS1.3 Test Harness and Fixtures
Goal: Add deterministic fixture-based tests for fetch stage.
Owner: Coder C
Work packages: target 6-8
Interfaces: needs WS1.1 contract; provides CI-capable tests
Expected patches: 2 (fixtures, tests)

- WS1.4 Documentation Sync
Goal: Document acquisition stage usage and contract.
Owner: Coder D
Work packages: target 6-7
Interfaces: needs WS1.1+WS1.2 decisions; provides docs updates
Expected patches: 1-2 (README/docs)

### M2 workstreams
- WS2.1 Outline Parser Core
Goal: Parse JSONL and produce unconstrained summary outline.
Owner: Coder A
Work packages: target 6-10
Interfaces: needs `out/github_data.jsonl`; provides `out/outline.json` and/or `out/outline.txt`
Expected patches: 2-3

- WS2.2 Outline Determinism and Ranking
Goal: Ensure stable ordering and reproducible outline sections.
Owner: Coder B
Work packages: target 6-8
Interfaces: needs WS2.1 output; provides deterministic ranking logic
Expected patches: 2

- WS2.3 Outline Tests
Goal: Add parser and regression tests for outline content integrity.
Owner: Coder C
Work packages: target 6-8
Interfaces: needs WS2.1+WS2.2; provides test coverage and gate commands
Expected patches: 2

- WS2.4 Outline Docs and Examples
Goal: Document outline schema and examples.
Owner: Coder D
Work packages: target 6-7
Interfaces: needs WS2.1 contract; provides docs examples
Expected patches: 1

### M3 workstreams
- WS3.1 Blog Renderer
Goal: Generate <=500-word blog post from outline.
Owner: Coder E
Work packages: target 6-9
Interfaces: needs outline contract; provides `out/blog_post.md`
Expected patches: 2

- WS3.2 Bluesky Renderer
Goal: Generate <=140-character post from outline.
Owner: Coder F
Work packages: target 6-8
Interfaces: needs outline contract; provides `out/bluesky_post.txt`
Expected patches: 1-2

- WS3.3 Podcast Script Renderer
Goal: Generate <=500-word N-speaker script from outline.
Owner: Coder G
Work packages: target 6-10
Interfaces: needs outline contract and speaker policy; provides `out/podcast_script.txt`
Expected patches: 2-3

- WS3.4 Constraint Gates
Goal: Enforce channel limits and fail fast when exceeded.
Owner: Coder B
Work packages: target 6-8
Interfaces: needs WS3.1-WS3.3 outputs; provides verification commands for CI/local
Expected patches: 2

### M4 workstreams
- WS4.1 Multi-Speaker Audio Renderer
Goal: Convert N-speaker podcast script to audio artifact.
Owner: Coder H
Work packages: target 6-10
Interfaces: needs podcast script speaker tags and voice config; provides `out/episode.wav`
Expected patches: 2-3

- WS4.2 Audio Verification
Goal: Validate speaker mapping, output existence, and runtime error handling.
Owner: Coder C
Work packages: target 6-8
Interfaces: needs WS4.1 behavior; provides smoke tests and failure gates
Expected patches: 2

- WS4.3 Migration and Legacy Retirement
Goal: Deprecate legacy scripts after parity gates pass.
Owner: Coder D
Work packages: target 6-8
Interfaces: needs M1-M4 exit criteria; provides migration notes and retirement patch
Expected patches: 1-2

- WS4.4 Documentation and Release
Goal: Finalize docs, changelog entries, and closure artifacts.
Owner: Coder A
Work packages: target 6-7
Interfaces: needs all milestone outcomes; provides closure-quality docs
Expected patches: 1-2

## Per-milestone deliverables and done checks
### M1 deliverables and done checks
- Depends on: D1 (JSONL contract)
- Entry criteria: none
- Deliverables:
  - `fetch_github_data.py` with weekly JSONL output
  - JSONL schema/validation checks and fixtures
  - contract docs for JSONL fields
- Done checks:
  - `out/github_data.jsonl` produced with deterministic required fields
  - validation command exits 0 on valid fixtures and nonzero on malformed fixtures
  - acquisition tests pass in CI/local
- Exit criteria:
  - D1 contract implemented and validated
  - no blocker defects in acquisition path

### M2 deliverables and done checks
- Depends on: D1 (input contract), D2 (outline contract)
- Entry criteria:
  - M1 exit criteria satisfied
- Deliverables:
  - `outline_github_data.py`
  - outline schema and deterministic ordering checks
  - outline examples in docs
- Done checks:
  - outline stage handles full weekly JSONL without truncation
  - same input produces byte-stable ordering
  - parser/regression tests pass
- Exit criteria:
  - D2 contract implemented
  - outline output accepted by M3 renderers on smoke fixtures

### M3 deliverables and done checks
- Depends on: D2 (outline contract), D3 (constraint policy)
- Entry criteria:
  - M2 exit criteria satisfied
- Deliverables:
  - `outline_to_blog_post.py`
  - `outline_to_bluesky_post.py`
  - `outline_to_podcast_script.py`
  - shared constraint gate checks
- Done checks:
  - blog output <=500 words
  - bluesky output <=140 characters
  - podcast output <=500 words and valid N-speaker labeling
  - renderer + constraint tests pass
- Exit criteria:
  - D3 constraints enforced by tests, not only by documentation
  - outputs are consumable by M4 audio stage

### M4 deliverables and done checks
- Depends on: D3 (speaker constraints), D4 (audio contract), D5 (release gates)
- Entry criteria:
  - M3 exit criteria satisfied
- Deliverables:
  - `script_to_audio.py` for N-speaker scripts
  - audio smoke verification and failure semantics
  - migration notes and legacy retirement criteria
- Done checks:
  - audio artifact generated for valid N-speaker script
  - invalid speaker mappings fail with explicit actionable errors
  - release checklist passes end-to-end dry run
- Exit criteria:
  - D4 and D5 satisfied
  - legacy path marked deprecated (or removed if approved)

## Work package template (required)
Work package title: [Verb + object]
Owner: [Single coder]
Touch points: [files/components]
Acceptance criteria: [measurable outcomes]
Verification commands: [exact commands with pass/fail semantics]
Dependencies: [dependency IDs or work package IDs; use none when unblocked]

## Acceptance criteria and gates
- Unit gate: each new script has unit tests for core transforms and edge cases.
- Integration gate: one command runs stages in order from JSONL through audio on fixture data.
- Regression gate: legacy fixture set maintains stable outline ordering and limit enforcement.
- Release gate: docs updated, migration checklist complete, and all stage outputs generated in a clean environment.

## Test and verification strategy
- Unit checks:
  - parsing, normalization, and limit calculators for each stage.
- Integration checks:
  - staged run from `fetch_github_data.py` -> `outline_github_data.py` -> renderers -> `script_to_audio.py`.
- Smoke/system checks:
  - minimal fixture run validating all expected output files under `out/`.
- Full regression checks:
  - repeatable outputs for fixed fixture snapshots, including deterministic ordering checks.
- Failure semantics:
  - any gate failure blocks milestone exit and release progression.

## Migration and compatibility policy
- Additive rollout policy:
  - New stage scripts ship alongside legacy scripts first.
  - Legacy scripts remain supported until M4 release gate passes.
- Compatibility promises:
  - `GITHUB_USER`, `WINDOW_DAYS`, and `OUTPUT_DIR` env vars remain valid unless replaced with documented aliases.
  - Existing `voices.json` remains readable through transition.
- Legacy deletion criteria:
  - remove/deprecate `fetch_and_script.py` and `tts_generate.py` only after:
    - end-to-end parity run is validated
    - docs point to new flow
    - rollback path is documented
- Rollback:
  - fallback to legacy scripts by restoring prior entrypoint commands in docs and workflow.

## Risk register and mitigations
- Risk: GitHub rate limits or API variability break acquisition.
Impact: High
Trigger: failed fetch responses or incomplete pagination
Owner: WS1.1 owner
Mitigation: token support, retry/backoff policy, explicit fetch completeness checks

- Risk: Outline quality drift causes poor downstream outputs.
Impact: High
Trigger: unstable ranking/ordering across runs
Owner: WS2.2 owner
Mitigation: deterministic ordering rules and regression fixtures

- Risk: Constraint violations slip through (word/character/speaker limits).
Impact: High
Trigger: outputs exceed limits in production runs
Owner: WS3.4 owner
Mitigation: hard gate checks with fail-fast semantics in CI/local

- Risk: Multi-speaker script tags do not map cleanly to TTS voices.
Impact: Medium
Trigger: missing speaker labels or undefined voice mappings
Owner: WS4.1 owner
Mitigation: strict parser for speaker tags and explicit mapping validation

- Risk: Plan-to-implementation drift.
Impact: Medium
Trigger: patches merged without mapping to work packages
Owner: Manager
Mitigation: patch reporting format enforced in weekly status updates

## Rollout and release checklist
- Approve D1-D5 dependency decisions.
- Complete M1-M4 exit criteria without open blocker defects.
- Run full staged integration with fixture and live sample.
- Verify all output constraints and speaker mapping gates.
- Update README + docs with final commands and file contracts.
- Record closure in plan tracker and changelog.

## Documentation close-out requirements
- Keep this plan in `docs/active_plans/` until all milestones close.
- Add per-milestone progress notes (Patch IDs, gate status, blockers).
- Add implementation summary to `docs/CHANGELOG.md` using Patch labels.
- On completion, archive this plan either by:
  - moving to `docs/archive/` if that folder exists, or
  - adding a closure section in-place for small repos that do not maintain an archive folder.
- Add/update `refactor_progress.md` so future planning has baseline context.

## Patch plan and reporting format
- Patch 1: data_acquisition_component establish JSONL fetch contract and writer
- Patch 2: verification_component add JSONL schema validation and fixtures
- Patch 3: outline_synthesis_component implement parser and deterministic ordering
- Patch 4: channel_rendering_component add blog and bluesky renderers with gates
- Patch 5: channel_rendering_component add N-speaker podcast renderer with gates
- Patch 6: audio_rendering_component implement script-to-audio with speaker mapping
- Patch 7: docs_release_component migration notes, changelog, and plan closure artifacts
- Patch N: tests, migration, docs

## Open questions and decisions needed
- Decision needed (Owner: user/manager): exact JSONL schema breadth (repo events only vs commits/issues/PR metadata included by default).
- Decision needed (Owner: user/manager): preferred outline format (`.json`, `.md`, or both) as canonical downstream input.
- Decision needed (Owner: user/manager): enforce hard truncation vs reject-on-overflow for 500-word and 140-character constraints.
- Decision needed (Owner: user/manager): default `NUM_SPEAKERS` when not provided.
- Decision needed (Owner: user/manager): audio output target format requirements (`.wav` only vs `.wav` + `.mp3`).
