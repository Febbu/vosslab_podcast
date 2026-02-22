# Vosslab Weekly Podcast Digest

Generates a weekly multi-channel content package from GitHub activity.

## Process flow
1. `pipeline/fetch_github_data.py`
- Fetch all relevant GitHub activity data and write a large JSONL file.
2. `pipeline/outline_github_data.py`
- Parse the large JSONL file and write a summary outline (no length limit).
3. Content generation from outline
- `pipeline/outline_to_blog_post.py`: write an LLM-generated Markdown blog post for MkDocs (target 500 words).
- `pipeline/outline_to_bluesky_post.py`: write an LLM-generated Bluesky post (target 140 characters; final output is publish-safe trimmed).
- `pipeline/outline_to_podcast_script.py`: write an LLM-generated N-speaker podcast script (target 500 words; final output is trimmed to fit).
4. Audio rendering
- `pipeline/script_to_audio.py`: multi-speaker Qwen TTS (`out/episode.wav`).
- `pipeline/script_to_audio_say.py`: single-speaker macOS `say`/Siri-style render (`out/episode_siri.aiff`).

## Output files
- `out/github_data.jsonl` (raw collected GitHub data)
- `out/daily_cache/github_data_YYYY-MM-DD.jsonl` (one cache JSONL per day in window)
- `out/outline.json` and `out/outline.txt` (summary outline)
- `out/outline_repos/index.json` (manifest of per-repo outline shards)
- `out/outline_repos/*.json` and `out/outline_repos/*.txt` (one shard per repo)
- `out/blog_post_YYYY-MM-DD.md` (Markdown blog post, date-stamped filename, target 500 words)
- `out/bluesky_post.txt` (<= 140 characters)
- `out/podcast_script.txt` (<= 500 words, N speakers)
- `out/blog_repo_drafts/*.json` (per-repo cached blog intermediate drafts)
- `out/bluesky_repo_drafts/*.json` (per-repo cached Bluesky intermediate drafts)
- `out/podcast_repo_drafts/*.json` (per-repo cached podcast intermediate drafts)
- `out/episode.wav` (or equivalent audio output)
- `out/episode_siri.aiff` (optional single-speaker macOS `say` output)

## Usage (local)
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r pip_requirements.txt
python pipeline/fetch_github_data.py --settings settings.yaml --last-week
python pipeline/outline_github_data.py --settings settings.yaml --repo-shards-dir out/outline_repos
python pipeline/outline_to_blog_post.py
python pipeline/outline_to_bluesky_post.py
python pipeline/outline_to_podcast_script.py --num-speakers 3
```

## Settings file
Use root `settings.yaml` for default user and LLM preferences:
```yaml
github:
  username: vosslab
  token: ""

llm:
  max_tokens: 1200
  repo_limit: 0
  providers:
    apple:
      enabled: true
    ollama:
      enabled: false
      models:
        - name: "qwen2.5:7b"
          enabled: true
        - name: "llama3.2:3b"
          enabled: false

tts:
  say:
    voice: "Siri"
    rate_wpm: 185
```

CLI flags still override settings values when provided.

## LLM outline summarization
- `pipeline/outline_github_data.py` uses `local-llm-wrapper` to generate:
  - `llm_repo_outline` for each repo
  - `llm_global_outline` for the overall week
- `pipeline/outline_to_blog_post.py`, `pipeline/outline_to_bluesky_post.py`, and
  `pipeline/outline_to_podcast_script.py` now also use `local-llm-wrapper`.
- Recommended placement for vendored wrapper code: repo root at `local-llm-wrapper/`.
- `pipeline/local-llm-wrapper/` is also supported by the loader if you move it later.
- `apple-foundation-models` is a required Python dependency in `pip_requirements.txt`.
- Provider names for local-llm-wrapper are `apple` and `ollama`.
- Default transport comes from `settings.yaml` enabled providers under `llm.providers`.
- Exactly one provider should have `enabled: true`; if multiple are enabled, outline generation fails.
- Apple provider does not use a model setting.
- If Ollama is enabled, configure `llm.providers.ollama.models` and enable exactly one model.
- Useful options:
  - `--llm-transport ollama|apple|auto`
  - `--llm-model <model-name>`
  - `--llm-max-tokens <int>`
  - `--llm-repo-limit <int>`
  - `--continue` (default) / `--no-continue` for per-repo draft cache reuse in `outline_to_*` stages
  - `--repo-draft-cache-dir <path>` for stage-specific intermediate draft cache location

## Outline sharding for LLM token limits
- `pipeline/outline_github_data.py` writes one outline shard per repo by default.
- Each shard has both JSON and text outputs under `out/outline_repos/`.
- Use `out/outline_repos/index.json` to iterate repos and summarize each shard independently.
- Continue mode is enabled by default and reuses existing repo shard outlines to avoid regenerating
  already-complete repo summaries.
- Optional flags:
  - `--repo-shards-dir <path>` to change shard output location.
  - `--skip-repo-shards` to disable shard output.
  - `--no-continue` to force regeneration of all repo outlines.

## Fetch stage notes
- Default user comes from `settings.yaml` (`github.username`), with fallback to `vosslab`.
- Window presets are `--last-day` (default), `--last-week`, or `--last-month`.
- `pipeline/fetch_github_data.py` attempts to fetch `docs/CHANGELOG.md` for relevant repos and writes
  `repo_changelog` records when available.
- Daily cache files are written by default to `out/daily_cache/`.
- Use `--daily-cache-dir <path>` to change cache location.
- Use `--skip-changelog` to skip changelog fetches.

## Optional auth
- Put an optional PAT in `settings.yaml` as `github.token`.
- If `github.token` is empty, fetch runs in unauthenticated mode with lower rate limits.

## GitHub Actions
A workflow is included in `.github/workflows/weekly.yml` for optional manual runs.

To enable:
1. Push this repo to GitHub.
2. Provide a token in `settings.yaml` (`github.token`) if you want higher rate limits.
3. This repo is currently local-first: no cron schedule is enabled by default.

## TTS (local, optional)
Use `pipeline/script_to_audio.py` to read `out/podcast_script.txt` and generate `out/episode.wav`.

### TTS environment (Conda)
```bash
conda create -n qwen3-tts python=3.12 -y
conda activate qwen3-tts
pip install -r pip_requirements.txt
```

### Generate audio
```bash
conda activate qwen3-tts
python pipeline/script_to_audio.py --script out/podcast_script.txt --output out/episode.wav
```

### Generate single-speaker audio with macOS say (Siri-style)
This backend renders one voice only and collapses multi-speaker script lines into a single narration.

```bash
python pipeline/script_to_audio_say.py --settings settings.yaml --script out/podcast_script.txt --output out/episode_siri.aiff --voice Siri
```

List installed voices:

```bash
python pipeline/script_to_audio_say.py --list-voices
```

## Local launchd scheduling (macOS)
- Runner script: `automation/run_local_pipeline.sh`
- Install launchd job: `automation/install_launchd_pipeline.sh`
- Remove launchd job: `automation/uninstall_launchd_pipeline.sh`

Commands:
```bash
chmod +x automation/run_local_pipeline.sh automation/install_launchd_pipeline.sh automation/uninstall_launchd_pipeline.sh
./automation/install_launchd_pipeline.sh
```

## Homebrew setup (macOS)
Install system dependencies:
```bash
brew bundle --file Brewfile
```

### Voice config
Edit `voices.json`.

- Legacy keys are supported: `host_voice`, `analyst_voice`, `guest_voice`, `guest_voice_override`.
- Preferred key for N-speaker scripts: `speaker_map`.

Example:
```json
{
  "speaker_map": {
    "SPEAKER_1": "speaker_1",
    "SPEAKER_2": "speaker_2",
    "SPEAKER_3": "speaker_3"
  }
}
```
