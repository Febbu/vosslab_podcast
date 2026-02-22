#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

if [[ ! -x "$REPO_ROOT/.venv/bin/python" ]]; then
	echo "Missing virtual environment python: $REPO_ROOT/.venv/bin/python"
	echo "Create it first: python3 -m venv .venv && .venv/bin/pip install -r pip_requirements.txt"
	exit 1
fi

source "$REPO_ROOT/source_me.sh"

"$REPO_ROOT/.venv/bin/python" pipeline/fetch_github_data.py --settings settings.yaml --last-week --output out/github_data.jsonl --daily-cache-dir out/daily_cache
"$REPO_ROOT/.venv/bin/python" pipeline/outline_github_data.py --settings settings.yaml --input out/github_data.jsonl --outline-json out/outline.json --outline-txt out/outline.txt
"$REPO_ROOT/.venv/bin/python" pipeline/outline_to_blog_post.py --input out/outline.json --output out/blog_post.html --word-limit 500
"$REPO_ROOT/.venv/bin/python" pipeline/outline_to_bluesky_post.py --input out/outline.json --output out/bluesky_post.txt --char-limit 140
"$REPO_ROOT/.venv/bin/python" pipeline/outline_to_podcast_script.py --input out/outline.json --output out/podcast_script.txt --num-speakers 3 --word-limit 500

echo "Pipeline run complete: $REPO_ROOT/out"
