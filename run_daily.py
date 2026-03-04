#!/usr/bin/env python3
from __future__ import annotations

import argparse
import random
import subprocess
import sys
import time


def _run(cmd: list[str]) -> None:
    print("+", " ".join(cmd))
    subprocess.run(cmd, check=True)


def _run_with_retry(
    stage_name: str,
    cmd: list[str],
    max_retries: int,
    retry_wait_seconds: float,
) -> None:
    attempt = 0
    while True:
        attempt += 1
        print(f"[run_daily] stage={stage_name} attempt={attempt}/{max_retries + 1}")
        try:
            _run(cmd)
            return
        except subprocess.CalledProcessError:
            if attempt > max_retries:
                raise
            wait_seconds = retry_wait_seconds + random.random()
            print(f"[run_daily] stage={stage_name} failed, retrying in {wait_seconds:.1f}s")
            time.sleep(wait_seconds)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run daily modular podcast pipeline.")
    parser.add_argument("--date", dest="run_date", help="Run date in YYYY-MM-DD. Defaults to today.")
    parser.add_argument("--logs", default="logs/latest.jsonl", help="Logs file for step 01.")
    parser.add_argument("--source", choices=["github", "logs"], default="github", help="Input source for step 01.")
    parser.add_argument("--github-user", default="vosslab", help="GitHub username when --source github.")
    parser.add_argument("--timezone", default="America/Chicago", help="Timezone for daily boundary in step 01.")
    parser.add_argument("--data-dir", default="data", help="Artifact root directory.")
    parser.add_argument("--audio-engine", choices=["dry-run", "qwen", "kokoro", "apple"], default="dry-run")
    parser.add_argument("--apple-voice", default=None, help="Apple voice override when --audio-engine apple.")
    parser.add_argument("--kokoro-voice", default="am_puck", help="Kokoro voice id when --audio-engine kokoro.")
    parser.add_argument("--kokoro-speed", type=float, default=1.0, help="Kokoro speed when --audio-engine kokoro.")
    parser.add_argument("--mp3", action="store_true", help="Also generate mp3 in step 04.")
    parser.add_argument("--presenters", type=int, choices=[1, 2], default=1, help="Presenters count for step 03.")
    parser.add_argument("--max-retries", type=int, default=1, help="Retries per stage on failure. Default: 1")
    parser.add_argument(
        "--retry-wait-seconds",
        type=float,
        default=4.0,
        help="Base wait between retries. Random jitter is added. Default: 4.0",
    )
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
    _run_with_retry("01_logs_to_outline", step1, args.max_retries, args.retry_wait_seconds)
    _run_with_retry(
        "02_outline_to_blog",
        [sys.executable, "pipelines/02_outline_to_blog.py", *common_args],
        args.max_retries,
        args.retry_wait_seconds,
    )
    _run_with_retry(
        "03_blog_to_script",
        [sys.executable, "pipelines/03_blog_to_script.py", "--presenters", str(args.presenters), *common_args],
        args.max_retries,
        args.retry_wait_seconds,
    )
    audio_cmd = [sys.executable, "pipelines/04_script_to_audio.py", "--engine", args.audio_engine, *common_args]
    if args.apple_voice:
        audio_cmd.extend(["--apple-voice", args.apple_voice])
    if args.audio_engine == "kokoro":
        audio_cmd.extend(["--kokoro-voice", args.kokoro_voice, "--kokoro-speed", str(args.kokoro_speed)])
    if args.mp3:
        audio_cmd.append("--mp3")
    _run_with_retry("04_script_to_audio", audio_cmd, args.max_retries, args.retry_wait_seconds)


if __name__ == "__main__":
    main()
