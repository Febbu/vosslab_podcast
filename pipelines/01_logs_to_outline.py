#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import requests

from common import resolve_run_context


def _load_events(logs_path: Path) -> list[dict[str, Any]]:
    if not logs_path.exists():
        return []

    if logs_path.suffix == ".jsonl":
        events: list[dict[str, Any]] = []
        with logs_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                events.append(json.loads(line))
        return events

    if logs_path.suffix == ".json":
        payload = json.loads(logs_path.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            return payload
        return [payload]

    raise ValueError(f"Unsupported log format: {logs_path}")


def _parse_iso(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _fetch_repos(user: str, sort: str, token: str | None) -> list[dict[str, Any]]:
    url = f"https://api.github.com/users/{user}/repos?per_page=100&sort={sort}"
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list):
        raise RuntimeError("Unexpected GitHub API payload")
    return payload


def _github_repo_events_for_day(
    user: str,
    run_date: str,
    token: str | None,
    timezone_name: str,
) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    tz = ZoneInfo(timezone_name)
    day_start_local = datetime.strptime(run_date, "%Y-%m-%d").replace(tzinfo=tz)
    day_end_local = day_start_local + timedelta(days=1)

    created = _fetch_repos(user, "created", token)
    pushed = _fetch_repos(user, "pushed", token)

    events: list[dict[str, Any]] = []
    created_repos: list[str] = []
    updated_repos: list[str] = []

    for repo in created:
        created_at = repo.get("created_at")
        if repo.get("fork") or not created_at:
            continue
        t_local = _parse_iso(created_at).astimezone(tz)
        repo_name = repo.get("full_name") or repo.get("name") or "unknown-repo"
        if day_start_local <= t_local < day_end_local:
            created_repos.append(repo_name)
            events.append(
                {
                    "actor": user,
                    "action": "created repository",
                    "target": repo_name,
                }
            )

    for repo in pushed:
        pushed_at = repo.get("pushed_at")
        if repo.get("fork") or not pushed_at:
            continue
        t_local = _parse_iso(pushed_at).astimezone(tz)
        repo_name = repo.get("full_name") or repo.get("name") or "unknown-repo"
        if day_start_local <= t_local < day_end_local:
            updated_repos.append(repo_name)
            events.append(
                {
                    "actor": user,
                    "action": "pushed updates to repository",
                    "target": repo_name,
                }
            )

    # Keep API order (newest first) while removing duplicates.
    created_unique: list[str] = []
    created_seen: set[str] = set()
    for name in created_repos:
        if name in created_seen:
            continue
        created_seen.add(name)
        created_unique.append(name)

    updated_unique: list[str] = []
    updated_seen: set[str] = set()
    for name in updated_repos:
        if name in updated_seen:
            continue
        updated_seen.add(name)
        updated_unique.append(name)

    return events, created_unique, updated_unique


def build_outline(
    events: list[dict[str, Any]],
    run_date: str,
    source_name: str,
    story_angle: str,
    created_repos: list[str] | None = None,
    updated_repos: list[str] | None = None,
) -> dict[str, Any]:
    created_repos = created_repos or []
    updated_repos = updated_repos or []

    top_points: list[str] = []
    top_points.append(f"New repos today: {len(created_repos)}")
    top_points.append(f"Updated repos today: {len(updated_repos)}")

    if created_repos:
        top_points.append(f"New repo highlights: {', '.join(created_repos[:8])}")
    if updated_repos:
        top_points.append(f"Updated repo highlights: {', '.join(updated_repos[:8])}")

    for event in events[:10]:
        actor = event.get("actor") or event.get("user") or "unknown-actor"
        action = event.get("action") or event.get("event") or "did something"
        target = event.get("target") or event.get("repo") or event.get("object") or "unknown-target"
        top_points.append(f"{actor} {action} on {target}")

    if not top_points:
        top_points = [
            "No structured logs were found for this date.",
            "Keep this outline step as-is and plug in Claude/Codex log parsing next.",
        ]

    return {
        "date": run_date,
        "source": source_name,
        "event_count": len(events),
        "created_count": len(created_repos),
        "updated_count": len(updated_repos),
        "created_repos": created_repos,
        "updated_repos": updated_repos,
        "top_points": top_points,
        "story_angle": story_angle,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert daily logs into an outline artifact.")
    parser.add_argument("--date", dest="run_date", help="Run date in YYYY-MM-DD. Defaults to today.")
    parser.add_argument(
        "--logs",
        default="logs/latest.jsonl",
        help="Path to logs file (.jsonl or .json). Default: logs/latest.jsonl",
    )
    parser.add_argument(
        "--source",
        choices=["github", "logs"],
        default="github",
        help="Input source for step 1. Default: github",
    )
    parser.add_argument("--github-user", default="vosslab", help="GitHub username for --source github")
    parser.add_argument(
        "--timezone",
        default="America/Chicago",
        help="Timezone for day boundaries (IANA). Default: America/Chicago",
    )
    parser.add_argument("--data-dir", default="data", help="Artifact root directory. Default: data")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    context = resolve_run_context(data_dir, args.run_date)
    story_angle = "Build progress, blockers, and what changed today."

    if args.source == "github":
        token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
        events, created_repos, updated_repos = _github_repo_events_for_day(
            args.github_user,
            context.run_date,
            token,
            args.timezone,
        )
        source_name = f"github:{args.github_user}:{args.timezone}"
        story_angle = f"Repository activity summary for the selected day in {args.timezone}."
    else:
        logs_path = Path(args.logs)
        events = _load_events(logs_path)
        created_repos = []
        updated_repos = []
        source_name = str(logs_path)

    outline = build_outline(
        events,
        context.run_date,
        source_name,
        story_angle,
        created_repos=created_repos,
        updated_repos=updated_repos,
    )

    out_path = context.run_dir / "outline.json"
    out_path.write_text(json.dumps(outline, indent=2), encoding="utf-8")
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
