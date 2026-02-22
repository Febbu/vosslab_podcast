#!/usr/bin/env python3
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import requests


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _in_window(ts: str, window_start: datetime, window_end: datetime) -> bool:
    if not ts:
        return False
    t = _parse_iso(ts)
    return window_start <= t <= window_end


def _fetch_repos(user: str, sort: str, token: str | None) -> List[Dict[str, Any]]:
    url = f"https://api.github.com/users/{user}/repos?per_page=100&sort={sort}"
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, list):
        raise RuntimeError("Unexpected GitHub API response format.")
    return data


def _summarize_repo(repo: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "name": repo.get("name"),
        "full_name": repo.get("full_name"),
        "html_url": repo.get("html_url"),
        "description": repo.get("description"),
        "language": repo.get("language"),
        "created_at": repo.get("created_at"),
        "pushed_at": repo.get("pushed_at"),
    }


def _render_script(digest: Dict[str, Any]) -> str:
    window_start = digest["window_start"]
    window_end = digest["window_end"]
    new_repos = digest["new_repos"]
    updated = digest["updated_repos"]

    def pick_names(items: List[Dict[str, Any]], limit: int = 5) -> str:
        names = [i["name"] for i in items[:limit] if i.get("name")]
        return ", ".join(names)

    lines: List[str] = []
    lines.append(
        f"HOST: Welcome back to the Vosslab weekly repo roundup for {window_start} through {window_end}."
    )
    if new_repos:
        lines.append(
            f"ANALYST: {len(new_repos)} new repos this week. Highlights: {pick_names(new_repos, 6)}."
        )
    else:
        lines.append("ANALYST: No new repos this week, but there were updates.")

    if updated:
        lines.append(
            f"GUEST: Updated repos include {pick_names(updated, 8)}."
        )
    else:
        lines.append("GUEST: No repo-level pushes recorded in the last 7 days.")

    lines.append("HOST: That's the week. See you next episode.")
    return "\n".join(lines) + "\n"


def main() -> None:
    user = os.getenv("GITHUB_USER", "vosslab")
    window_days = int(os.getenv("WINDOW_DAYS", "7"))
    output_dir = os.getenv("OUTPUT_DIR", "out")
    token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")

    now = _utc_now()
    window_start = now - timedelta(days=window_days)

    created_list = _fetch_repos(user, "created", token)
    pushed_list = _fetch_repos(user, "pushed", token)

    new_repos = [
        _summarize_repo(r)
        for r in created_list
        if not r.get("fork") and _in_window(r.get("created_at"), window_start, now)
    ]
    new_repos.sort(key=lambda r: r.get("created_at") or "", reverse=True)

    updated_repos = [
        _summarize_repo(r)
        for r in pushed_list
        if not r.get("fork") and _in_window(r.get("pushed_at"), window_start, now)
    ]
    updated_repos.sort(key=lambda r: r.get("pushed_at") or "", reverse=True)

    digest = {
        "window_start": window_start.strftime("%Y-%m-%d"),
        "window_end": now.strftime("%Y-%m-%d"),
        "new_repos": new_repos,
        "updated_repos": updated_repos,
    }

    os.makedirs(output_dir, exist_ok=True)
    digest_path = os.path.join(output_dir, "digest.json")
    script_path = os.path.join(output_dir, "script.txt")

    with open(digest_path, "w", encoding="utf-8") as f:
        json.dump(digest, f, indent=2)
        f.write("\n")

    script = _render_script(digest)
    with open(script_path, "w", encoding="utf-8") as f:
        f.write(script)

    print(f"Wrote {digest_path}")
    print(f"Wrote {script_path}")


if __name__ == "__main__":
    main()
