# Vosslab Weekly Podcast Digest

Generates a weekly multi-channel content package from GitHub activity.

## Process flow
1. `fetch_github_data.py`
- Fetch all relevant GitHub activity data and write a large JSONL file.
2. `outline_github_data.py`
- Parse the large JSONL file and write a summary outline (no length limit).
3. Content generation from outline
- `outline_to_blog_post.py`: write a webpage blog post (max 500 words).
- `outline_to_bluesky_post.py`: write a Bluesky post (max 140 characters).
- `outline_to_podcast_script.py`: write an N-speaker podcast script (max 500 words).
4. `script_to_audio.py`
- Convert the N-speaker podcast script into an audio file using TTS.

## Planned outputs
- `out/github_data.jsonl` (raw collected GitHub data)
- `out/outline.json` or `out/outline.txt` (summary outline)
- `out/blog_post.md` (<= 500 words)
- `out/bluesky_post.txt` (<= 140 characters)
- `out/podcast_script.txt` (<= 500 words, N speakers)
- `out/episode.wav` (or equivalent audio output)

## Usage (local)
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# Current implemented entry point (legacy flow):
python fetch_and_script.py
```

## Environment variables
- `GITHUB_USER` (default: `vosslab`)
- `WINDOW_DAYS` (default: `7`)
- `OUTPUT_DIR` (default: `out`)
- `GITHUB_TOKEN` or `GH_TOKEN` (optional, for higher rate limits)
- `NUM_SPEAKERS` (planned, used by `outline_to_podcast_script.py` and `script_to_audio.py`)

## GitHub Actions
A weekly workflow is included in `.github/workflows/weekly.yml`.

To enable:
1. Push this repo to GitHub.
2. Add a repository secret `GH_TOKEN` (a GitHub PAT) if you want higher rate limits.
3. The schedule can be edited in the workflow file.

## TTS (local, optional)
This project currently includes `tts_generate.py` to read `out/script.txt` and generate `out/episode.wav` using Qwen3-TTS. The planned pipeline replaces this with `script_to_audio.py` reading `out/podcast_script.txt`.

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
