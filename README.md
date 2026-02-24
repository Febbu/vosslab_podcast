# Vosslab Weekly Podcast Digest

Generates a weekly GitHub repo digest and a simple podcast-style script.

## What it does
- Fetches repos from GitHub (created + pushed)
- Filters to last 7 days
- Excludes forks
- Writes `out/digest.json` and `out/script.txt`

## Usage (local)
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python fetch_and_script.py
```

## Environment variables
- `GITHUB_USER` (default: `vosslab`)
- `WINDOW_DAYS` (default: `7`)
- `OUTPUT_DIR` (default: `out`)
- `GITHUB_TOKEN` or `GH_TOKEN` (optional, for higher rate limits)

## GitHub Actions
A weekly workflow is included in `.github/workflows/weekly.yml`.

To enable:
1. Push this repo to GitHub.
2. Add a repository secret `GH_TOKEN` (a GitHub PAT) if you want higher rate limits.
3. The schedule can be edited in the workflow file.

## TTS (local, optional)
This project includes `tts_generate.py` to read `out/script.txt` and generate `out/episode.wav` using Qwen3‑TTS. The recommended path is to install the official `qwen-tts` package in a clean Python 3.12 environment and use the lightweight CustomVoice model. citeturn0search0turn1search0

### TTS environment (Conda)
```bash
conda create -n qwen3-tts python=3.12 -y
conda activate qwen3-tts
pip install -U qwen-tts soundfile
```
citeturn0search0

### Generate audio
```bash
conda activate qwen3-tts
python tts_generate.py
```

### Voice config
Edit `voices.json` to keep consistent roles. Set `guest_voice_override` when you want a different guest speaker for a specific episode.

## Daily Modular Pipeline (Scaffold)
Steps are intentionally independent and artifact-based:

1. `logs -> outline` via `pipelines/01_logs_to_outline.py`
2. `outline -> blog` via `pipelines/02_outline_to_blog.py`
3. `blog -> script` via `pipelines/03_blog_to_script.py`
4. `script -> audio` via `pipelines/04_script_to_audio.py`

Artifacts are written under `data/YYYY-MM-DD/`.

### Run steps 1 and 2
```bash
python pipelines/01_logs_to_outline.py --date 2026-02-24 --source github --github-user vosslab
python pipelines/02_outline_to_blog.py --date 2026-02-24
python pipelines/03_blog_to_script.py --date 2026-02-24 --presenters 1
python pipelines/04_script_to_audio.py --date 2026-02-24 --engine dry-run
```

### Apple TTS (recommended fallback on macOS)
```bash
python pipelines/04_script_to_audio.py --date 2026-02-24 --engine apple --mp3
```
Outputs:
- `data/YYYY-MM-DD/episode.aiff`
- `data/YYYY-MM-DD/episode.mp3`

### One-command run
```bash
python run_daily.py --date 2026-02-24 --source github --github-user vosslab --timezone America/Chicago --presenters 1 --audio-engine dry-run
python run_daily.py --date 2026-02-17 --source github --github-user vosslab --timezone America/Chicago --presenters 1 --audio-engine apple --mp3
```
