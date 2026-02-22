# Vosslab Weekly Podcast Digest

Generates a weekly multi-channel content package from GitHub activity.

## Process flow
1. `pipeline/fetch_github_data.py`
- Fetch all relevant GitHub activity data and write a large JSONL file.
2. `pipeline/outline_github_data.py`
- Parse the large JSONL file and write a summary outline (no length limit).
3. Content generation from outline
- `pipeline/outline_to_blog_post.py`: write a webpage blog post (max 500 words).
- `pipeline/outline_to_bluesky_post.py`: write a Bluesky post (max 140 characters).
- `pipeline/outline_to_podcast_script.py`: write an N-speaker podcast script (max 500 words).
4. `pipeline/script_to_audio.py`
- Convert the N-speaker podcast script into an audio file using TTS.

## Output files
- `out/github_data.jsonl` (raw collected GitHub data)
- `out/daily_cache/github_data_YYYY-MM-DD.jsonl` (one cache JSONL per day in window)
- `out/outline.json` and `out/outline.txt` (summary outline)
- `out/outline_repos/index.json` (manifest of per-repo outline shards)
- `out/outline_repos/*.json` and `out/outline_repos/*.txt` (one shard per repo)
- `out/blog_post.html` (<= 500 words)
- `out/bluesky_post.txt` (<= 140 characters)
- `out/podcast_script.txt` (<= 500 words, N speakers)
- `out/episode.wav` (or equivalent audio output)

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

llm:
  transport: ollama
  model: ""
  max_tokens: 1200
  repo_limit: 0
```

CLI flags still override settings values when provided.

## LLM outline summarization
- `pipeline/outline_github_data.py` uses `local-llm-wrapper` to generate:
  - `llm_repo_outline` for each repo
  - `llm_global_outline` for the overall week
- Recommended placement for vendored wrapper code: repo root at `local-llm-wrapper/`.
- `pipeline/local-llm-wrapper/` is also supported by the loader if you move it later.
- `apple-foundation-models` is a required Python dependency in `pip_requirements.txt`.
- Default transport comes from `settings.yaml` (`llm.transport`).
- Useful options:
  - `--llm-transport ollama|apple|auto`
  - `--llm-model <model-name>`
  - `--llm-max-tokens <int>`
  - `--llm-repo-limit <int>`

## Outline sharding for LLM token limits
- `pipeline/outline_github_data.py` writes one outline shard per repo by default.
- Each shard has both JSON and text outputs under `out/outline_repos/`.
- Use `out/outline_repos/index.json` to iterate repos and summarize each shard independently.
- Optional flags:
  - `--repo-shards-dir <path>` to change shard output location.
  - `--skip-repo-shards` to disable shard output.

## Fetch stage notes
- Default user comes from `settings.yaml` (`github.username`), with fallback to `vosslab`.
- Default window is `--last-day` (1 day) when no window flag is provided.
- Preset options are mutually exclusive:
  - `--last-day`
  - `--last-two-days`
  - `--last-week`
  - `--last-month`
- Custom window remains available via `--window-days N`.
- `pipeline/fetch_github_data.py` attempts to fetch `docs/CHANGELOG.md` for relevant repos and writes
  `repo_changelog` records when available.
- Daily cache files are written by default to `out/daily_cache/`.
- Use `--daily-cache-dir <path>` to change cache location.
- Use `--skip-changelog` to skip changelog fetches.

## Optional auth
- `pipeline/fetch_github_data.py` accepts `--token`.
- If `--token` is not provided, it falls back to `GH_TOKEN` then `GITHUB_TOKEN`.

## GitHub Actions
A workflow is included in `.github/workflows/weekly.yml` for optional manual runs.

To enable:
1. Push this repo to GitHub.
2. Add a repository secret `GH_TOKEN` (a GitHub PAT) if you want higher rate limits.
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
