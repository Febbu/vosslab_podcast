#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import sys


def _run(cmd: list[str]) -> None:
    print("+", " ".join(cmd))
    subprocess.run(cmd, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run daily modular podcast pipeline.")
    parser.add_argument("--date", dest="run_date", help="Run date in YYYY-MM-DD. Defaults to today.")
    parser.add_argument("--logs", default="logs/latest.jsonl", help="Logs file for step 01.")
    parser.add_argument("--source", choices=["github", "logs"], default="github", help="Input source for step 01.")
    parser.add_argument("--github-user", default="vosslab", help="GitHub username when --source github.")
    parser.add_argument("--timezone", default="America/Chicago", help="Timezone for daily boundary in step 01.")
    parser.add_argument("--data-dir", default="data", help="Artifact root directory.")
    parser.add_argument("--audio-engine", choices=["dry-run", "qwen", "apple"], default="dry-run")
    parser.add_argument("--mp3", action="store_true", help="Also generate mp3 in step 04.")
    parser.add_argument("--presenters", type=int, choices=[1, 2], default=1, help="Presenters count for step 03.")
    args = parser.parse_args()

    common_args: list[str] = []
    if args.run_date:
        common_args.extend(["--date", args.run_date])
    common_args.extend(["--data-dir", args.data_dir])

    step1 = [sys.executable, "pipelines/01_logs_to_outline.py", "--source", args.source, *common_args]
    if args.source == "github":
        step1.extend(["--github-user", args.github_user, "--timezone", args.timezone])
    else:
        step1.extend(["--logs", args.logs])
    _run(step1)
    _run([sys.executable, "pipelines/02_outline_to_blog.py", *common_args])
    _run([sys.executable, "pipelines/03_blog_to_script.py", "--presenters", str(args.presenters), *common_args])
    audio_cmd = [sys.executable, "pipelines/04_script_to_audio.py", "--engine", args.audio_engine, *common_args]
    if args.mp3:
        audio_cmd.append("--mp3")
    _run(audio_cmd)


if __name__ == "__main__":
    main()
