# OUT DIRECTORY ORGANIZATION SPEC

## Purpose
Define one stable, predictable layout for generated files under `out/` so:
- humans can quickly find outputs,
- scripts do not overwrite unrelated runs/users,
- future tooling can safely clean, archive, and diff outputs.

## Scope
This spec applies to all project scripts that read or write generated artifacts under `out/`.

## Core rule
All default script outputs and caches MUST be user-scoped:
- `out/<github_username>/...`

`<github_username>` comes from `settings.yaml` `github.username` unless overridden by CLI flags.

## Allowed top-level namespaces under `out/`
Only these top-level folders are allowed:
- `out/<github_username>/` for real pipeline runs.
- `out/logs/` for operational logs grouped by program.
- `out/smoke/` for smoke-test artifacts.
- `out/samples/` for tiny example fixtures checked or shared intentionally.
- `out/archive/` for manually archived historical outputs.
- `out/tmp/` for disposable local scratch data.

Any new top-level folder under `out/` should be treated as a spec violation unless documented here first.

## Logging layout
Logs are grouped by program/script and are not user-scoped by default:
- `out/logs/<program>/...`

Launchd exception:
- launchd jobs MAY use system log paths under `~/Library/Logs/<program>/...` on macOS.
- For this repo, launchd logs are written to:
- `~/Library/Logs/vosslab_podcast/launchd/launchd_pipeline.log`
- `~/Library/Logs/vosslab_podcast/launchd/launchd_pipeline.error.log`

Examples:
- `out/logs/fetch_github_data/fetch.log`
- `out/logs/outline_to_blog_post/blog.log`

## Required layout for `out/<github_username>/`
The following paths are the default contract:

- Fetch stage
- `out/<user>/github_data_YYYY-MM-DD.jsonl`
- `out/<user>/daily_cache/github_data_YYYY-MM-DD.jsonl`
- `out/<user>/cache/list_repos.json`
- `out/<user>/cache/github_api/` (filesystem query cache shards)

- Outline stage
- `out/<user>/outline.json`
- `out/<user>/outline.txt`
- `out/<user>/outline_repos/index.json`
- `out/<user>/outline_repos/*.json`
- `out/<user>/outline_repos/*.txt`

- Content stage
- `out/<user>/blog_post_YYYY-MM-DD.md`
- `out/<user>/bluesky_post.txt`
- `out/<user>/podcast_script.txt`

- Intermediate LLM drafts
- `out/<user>/blog_repo_drafts/*.json`
- `out/<user>/bluesky_repo_drafts/*.json`
- `out/<user>/podcast_repo_drafts/*.json`

- Audio stage
- `out/<user>/episode.wav`
- `out/<user>/episode_siri.aiff`

## Naming rules
- Use lowercase ASCII, numbers, underscores, and hyphens only.
- Date stamps use `YYYY-MM-DD`.
- Keep stable base names for machine consumption:
- `outline.json`, `outline.txt`, `bluesky_post.txt`, `podcast_script.txt`
- Use date-stamped filenames for fetch and blog outputs.

## Behavior rules for scripts
- If a script is run with default output/input paths, it MUST resolve to `out/<user>/...`.
- If a custom path is explicitly passed by CLI, the script MUST honor it as-is.
- Scripts SHOULD log resolved absolute input/output paths at startup.
- Scripts MUST NOT write default artifacts to bare `out/` root.
- Operational logs SHOULD be written under `out/logs/<program>/`.

## Cross-script compatibility
- Downstream scripts SHOULD default to user-scoped upstream outputs.
- Outline scripts SHOULD auto-discover latest matching user-scoped fetch file when applicable.

## Cleanup policy
- Safe cleanup targets:
- `out/tmp/`
- stale files in `out/smoke/`
- old dated files in `out/<user>/daily_cache/` and `out/<user>/cache/github_api/`

- Do not delete:
- latest `github_data_YYYY-MM-DD.jsonl`
- latest `outline.json`
- latest `blog_post_YYYY-MM-DD.md`
- any file outside `out/`

## Non-goals
- This spec does not define retention duration.
- This spec does not force commit of generated outputs.
- This spec does not change CLI override behavior.

## Migration note
Legacy files in bare `out/` may still exist from older runs. They are not canonical.
Current script defaults should write to `out/<user>/...`.
