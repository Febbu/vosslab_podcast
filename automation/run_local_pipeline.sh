#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

log_step() {
	local now_text
	now_text="$(date +"%H:%M:%S")"
	echo "[run_local_pipeline ${now_text}] $*"
}

log_step "Starting local pipeline run from $REPO_ROOT"

if [[ ! -x "$REPO_ROOT/.venv/bin/python" ]]; then
	log_step "Missing virtual environment python: $REPO_ROOT/.venv/bin/python"
	log_step "Create it first: python3 -m venv .venv && .venv/bin/pip install -r pip_requirements.txt"
	exit 1
fi

log_step "Sourcing runtime environment from source_me.sh"
source "$REPO_ROOT/source_me.sh"

log_step "Running fetch stage."
"$REPO_ROOT/.venv/bin/python" pipeline/fetch_github_data.py --settings settings.yaml --last-week --output out/github_data.jsonl --daily-cache-dir out/daily_cache
log_step "Running outline stage."
"$REPO_ROOT/.venv/bin/python" pipeline/outline_github_data.py --settings settings.yaml --input out/github_data.jsonl --outline-json out/outline.json --outline-txt out/outline.txt
log_step "Running blog output stage."
"$REPO_ROOT/.venv/bin/python" pipeline/outline_to_blog_post.py --input out/outline.json --output out/blog_post.html --word-limit 500
log_step "Running bluesky output stage."
"$REPO_ROOT/.venv/bin/python" pipeline/outline_to_bluesky_post.py --input out/outline.json --output out/bluesky_post.txt --char-limit 140
log_step "Running podcast script stage."
"$REPO_ROOT/.venv/bin/python" pipeline/outline_to_podcast_script.py --input out/outline.json --output out/podcast_script.txt --num-speakers 3 --word-limit 500

log_step "Pipeline run complete: $REPO_ROOT/out"
