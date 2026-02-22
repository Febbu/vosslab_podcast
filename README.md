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
This project includes `tts_generate.py` to read `out/script.txt` and generate `out/episode.wav` using Qwen3-TTS. The recommended path is to install the official `qwen-tts` package in a clean Python 3.12 environment and use the lightweight CustomVoice model. ?cite?turn0search0?turn1search0?

### TTS environment (Conda)
```bash
conda create -n qwen3-tts python=3.12 -y
conda activate qwen3-tts
pip install -r pip_requirements.txt
```

### Generate audio
```bash
conda activate qwen3-tts
python tts_generate.py
```

### Voice config
Edit `voices.json` to keep consistent roles. Set `guest_voice_override` when you want a different guest speaker for a specific episode.
