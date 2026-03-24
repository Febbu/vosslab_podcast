#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote
from zoneinfo import ZoneInfo

import requests

from common import resolve_run_context

README_CANDIDATES = ["README.md", "README.rst", "README.txt", "readme.md"]
CHANGELOG_CANDIDATES = ["docs/CHANGELOG.md", "CHANGELOG.md", "changelog.md", "docs/changelog.md"]
PROJECT_CONTEXT_FILES = ["pyproject.toml", "package.json", "Cargo.toml", "requirements.txt"]


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
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    all_repos: list[dict[str, Any]] = []
    page = 1
    while True:
        url = f"https://api.github.com/users/{user}/repos"
        response = requests.get(
            url,
            headers=headers,
            params={"per_page": 100, "sort": sort, "page": page},
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            raise RuntimeError("Unexpected GitHub API payload")
        if not payload:
            break
        all_repos.extend(payload)
        if len(payload) < 100:
            break
        page += 1
    return all_repos


def _github_get(url: str, token: str | None, params: dict[str, Any] | None = None) -> Any:
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    response = requests.get(url, headers=headers, params=params, timeout=30)
    response.raise_for_status()
    return response.json()


def _github_get_optional(url: str, token: str | None, params: dict[str, Any] | None = None) -> Any | None:
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    response = requests.get(url, headers=headers, params=params, timeout=30)
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return response.json()


def _fetch_repo_text_file(full_name: str, path: str, token: str | None) -> str | None:
    encoded = quote(full_name, safe="/")
    url = f"https://api.github.com/repos/{encoded}/contents/{quote(path)}"
    payload = _github_get_optional(url, token)
    if not isinstance(payload, dict):
        return None
    if payload.get("encoding") != "base64":
        return None
    content = payload.get("content")
    if not isinstance(content, str) or not content.strip():
        return None
    try:
        decoded = base64.b64decode(content).decode("utf-8", errors="replace")
    except Exception:
        return None
    return decoded


def _collapse_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _extract_readme_summary(readme_text: str) -> str | None:
    paragraphs = []
    current: list[str] = []
    for raw_line in readme_text.splitlines():
        line = raw_line.strip()
        if not line:
            if current:
                paragraphs.append(" ".join(current))
                current = []
            continue
        if line.startswith("#") or line.startswith("```"):
            continue
        current.append(line)
    if current:
        paragraphs.append(" ".join(current))
    for paragraph in paragraphs:
        cleaned = _collapse_whitespace(paragraph)
        if len(cleaned) >= 20:
            return cleaned[:220].rstrip()
    return None


def _extract_project_file_summary(path: str, text: str) -> str | None:
    cleaned_lines = [_collapse_whitespace(line) for line in text.splitlines() if line.strip()]
    if path == "package.json":
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            payload = {}
        name = str(payload.get("name") or "").strip()
        description = str(payload.get("description") or "").strip()
        if name and description:
            return f"{name}: {description}"[:220]
        if description:
            return description[:220]
    interesting = [
        line
        for line in cleaned_lines
        if any(marker in line.lower() for marker in ["description", "name", "dependencies", "requires", "version"])
    ]
    if interesting:
        return "; ".join(interesting[:3])[:220]
    if cleaned_lines:
        return " ".join(cleaned_lines[:3])[:220]
    return None


def _extract_changelog_summary(changelog_text: str) -> str | None:
    entries: list[str] = []
    for raw_line in changelog_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#"):
            if entries:
                break
            continue
        if line.startswith(("-", "*")):
            cleaned = _collapse_whitespace(line[1:].strip())
            if cleaned:
                entries.append(cleaned)
        elif not entries and len(line) > 20:
            entries.append(_collapse_whitespace(line))
        if len(entries) >= 3:
            break
    if not entries:
        return None
    return "; ".join(entries)[:280]


def _derive_repo_purpose(
    repo_name: str,
    description: str | None,
    readme_summary: str | None,
    project_context: list[str],
) -> str:
    if description and description.strip():
        return _collapse_whitespace(description)[:220]
    if readme_summary:
        return readme_summary[:220]
    if project_context:
        context = project_context[0]
        if ": " in context:
            context = context.split(": ", 1)[1]
        return context[:220]
    return f"{repo_name} is an active repository in the Vosslab workspace."


def _derive_change_summary(
    commit_messages: list[str],
    changelog_summary: str | None,
    top_files: list[str],
    areas_touched: list[str],
    change_types: list[str],
) -> str:
    if changelog_summary:
        return changelog_summary[:260]
    if len(commit_messages) >= 2:
        return f"Recent work included {commit_messages[0]}, and {commit_messages[1]}."
    if commit_messages:
        return f"The latest change was {commit_messages[0]}."
    if top_files:
        return f"Most of the work touched {', '.join(top_files[:3])}."
    if areas_touched or change_types:
        labels = ", ".join((change_types[:2] + areas_touched[:2])[:3])
        return f"The work focused on {labels}."
    return "It received updates during this reporting window."


def _derive_why_it_matters(
    top_files: list[str],
    areas_touched: list[str],
    change_types: list[str],
    additions: int,
    deletions: int,
) -> str:
    if top_files:
        return f"It mainly affected {', '.join(top_files[:3])}."
    if areas_touched:
        return f"It mainly affected the {', '.join(areas_touched[:3])} areas."
    if change_types:
        return f"It looks like {', '.join(change_types[:2])} work."
    if additions or deletions:
        return f"It was about {additions} additions and {deletions} deletions."
    return "It changed the current working state of the project."


def _fetch_repo_context(full_name: str, token: str | None) -> dict[str, Any]:
    readme_summary = None
    for candidate in README_CANDIDATES:
        text = _fetch_repo_text_file(full_name, candidate, token)
        if text:
            readme_summary = _extract_readme_summary(text)
            if readme_summary:
                break

    changelog_summary = None
    for candidate in CHANGELOG_CANDIDATES:
        text = _fetch_repo_text_file(full_name, candidate, token)
        if text:
            changelog_summary = _extract_changelog_summary(text)
            if changelog_summary:
                break

    project_context: list[str] = []
    for candidate in PROJECT_CONTEXT_FILES:
        text = _fetch_repo_text_file(full_name, candidate, token)
        if not text:
            continue
        summary = _extract_project_file_summary(candidate, text)
        if summary:
            project_context.append(f"{candidate}: {summary}")

    return {
        "readme_summary": readme_summary,
        "changelog_summary": changelog_summary,
        "project_context": project_context[:3],
    }


def _fetch_recent_commit_messages(
    full_name: str,
    token: str | None,
    limit: int = 3,
) -> list[str]:
    # Best-effort recent commit subjects for a repo on the selected day.
    encoded = quote(full_name, safe="/")
    url = f"https://api.github.com/repos/{encoded}/commits?per_page={limit}"
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    response = requests.get(url, headers=headers, timeout=30)
    if response.status_code >= 400:
        return []
    payload = response.json()
    if not isinstance(payload, list) or not payload:
        return []
    subjects: list[str] = []
    for commit in payload[:limit]:
        message = ((commit.get("commit") or {}).get("message") or "").strip()
        if not message:
            continue
        subject = message.splitlines()[0].strip()
        if subject:
            subjects.append(subject)
    return subjects


def _fetch_repo_commits_for_window(
    full_name: str,
    token: str | None,
    since_utc: datetime,
    until_utc: datetime,
    limit: int = 6,
) -> list[dict[str, Any]]:
    encoded = quote(full_name, safe="/")
    url = f"https://api.github.com/repos/{encoded}/commits"
    payload = _github_get(
        url,
        token,
        params={
            "per_page": limit,
            "since": since_utc.isoformat(),
            "until": until_utc.isoformat(),
        },
    )
    if not isinstance(payload, list):
        return []
    return payload[:limit]


def _commit_timestamp(commit_ref: dict[str, Any]) -> str | None:
    commit = commit_ref.get("commit") or {}
    committer = commit.get("committer") or {}
    author = commit.get("author") or {}
    value = str(committer.get("date") or author.get("date") or "").strip()
    return value or None


def _fetch_commit_detail(full_name: str, sha: str, token: str | None) -> dict[str, Any] | None:
    encoded = quote(full_name, safe="/")
    url = f"https://api.github.com/repos/{encoded}/commits/{sha}"
    try:
        payload = _github_get(url, token)
    except requests.HTTPError:
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def _extract_file_stats(commit_details: list[dict[str, Any]]) -> tuple[list[str], int, int]:
    file_names: list[str] = []
    additions = 0
    deletions = 0
    for detail in commit_details:
        for file_info in detail.get("files", []) or []:
            filename = str(file_info.get("filename") or "").strip()
            if filename:
                file_names.append(filename)
            additions += int(file_info.get("additions") or 0)
            deletions += int(file_info.get("deletions") or 0)
    return file_names, additions, deletions


def _extract_patch_snippets(commit_details: list[dict[str, Any]], limit: int = 3) -> list[str]:
    snippets: list[str] = []
    for detail in commit_details:
        for file_info in detail.get("files", []) or []:
            filename = str(file_info.get("filename") or "").strip()
            patch = str(file_info.get("patch") or "").strip()
            if not filename or not patch:
                continue
            condensed = _collapse_whitespace(patch.replace("@@", " "))
            if not condensed:
                continue
            snippets.append(f"{filename}: {condensed[:140].rstrip()}")
            if len(snippets) >= limit:
                return snippets
    return snippets


def _classify_area(filename: str) -> str:
    lower = filename.lower()
    if lower.startswith("tests/") or "/tests/" in lower:
        return "tests"
    if lower.startswith("docs/") or lower.endswith(".md"):
        return "docs"
    if "audio" in lower or "tts" in lower or "voice" in lower:
        return "audio"
    if "pipeline" in lower or "run_" in lower:
        return "pipeline"
    if lower.endswith(".json") or lower.endswith(".yaml") or lower.endswith(".yml") or "config" in lower:
        return "config"
    if "readme" in lower or "transcript" in lower:
        return "docs"
    return "code"


def _top_items(items: list[str], limit: int) -> list[str]:
    counts: dict[str, int] = {}
    positions: dict[str, int] = {}
    for item in items:
        if item not in counts:
            counts[item] = 0
            positions[item] = len(positions)
        counts[item] += 1
    ordered = list(counts)
    ordered.sort(key=lambda item: (-counts[item], positions[item]))
    return ordered[:limit]


def _detect_change_types(commit_messages: list[str], file_names: list[str]) -> list[str]:
    text = " ".join(commit_messages).lower()
    file_text = " ".join(file_names).lower()
    labels: list[str] = []
    if any(word in text for word in ["fix", "bug", "error", "correct", "repair"]):
        labels.append("bugfix")
    if any(word in text for word in ["add", "introduce", "support", "implement", "create"]):
        labels.append("feature")
    if any(word in text for word in ["refactor", "cleanup", "clean up", "reorganize"]):
        labels.append("refactor")
    if any(word in text for word in ["doc", "readme", "guide"]) or "docs/" in file_text:
        labels.append("docs")
    if any(word in text for word in ["test", "pytest"]) or "tests/" in file_text:
        labels.append("tests")
    if not labels:
        labels.append("maintenance")
    return labels


def _build_human_summary(
    repo_name: str,
    repo_purpose: str,
    change_summary: str,
    why_it_matters: str,
    changelog_summary: str | None,
    readme_summary: str | None,
    project_context: list[str],
    commit_messages: list[str],
    top_files: list[str],
    areas_touched: list[str],
    additions: int,
    deletions: int,
    patch_snippets: list[str],
) -> str:
    parts: list[str] = []
    parts.append(repo_purpose)
    parts.append(change_summary)
    parts.append(why_it_matters)
    if changelog_summary and changelog_summary not in change_summary:
        parts.append(f"the changelog highlights {changelog_summary}")
    if readme_summary and readme_summary not in repo_purpose:
        parts.append(readme_summary)
    elif project_context and project_context[0] not in repo_purpose:
        parts.append(project_context[0])
    if commit_messages and commit_messages[0] not in change_summary:
        if len(commit_messages) >= 2:
            parts.append(f"Recent work included {commit_messages[0]}, and {commit_messages[1]}")
        else:
            parts.append(f"Latest work was {commit_messages[0]}")
    if top_files:
        pretty_files = ", ".join(top_files[:3])
        parts.append(f"most of the change touched {pretty_files}")
    if areas_touched:
        parts.append(f"the main areas were {', '.join(areas_touched[:3])}")
    if additions or deletions:
        parts.append(f"roughly {additions} additions and {deletions} deletions")
    if patch_snippets:
        parts.append(f"one code hint was {patch_snippets[0]}")
    if not parts:
        return f"The {repo_name} repository had code changes."
    return f"The {repo_name} repository changed with " + "; ".join(parts) + "."


def _repo_card(
    repo: dict[str, Any],
    latest_commits: list[str] | None = None,
    readme_summary: str | None = None,
    changelog_summary: str | None = None,
    repo_purpose: str | None = None,
    change_summary: str | None = None,
    why_it_matters: str | None = None,
    project_context: list[str] | None = None,
    commit_count: int = 0,
    top_files: list[str] | None = None,
    areas_touched: list[str] | None = None,
    change_types: list[str] | None = None,
    additions: int = 0,
    deletions: int = 0,
    patch_snippets: list[str] | None = None,
    commit_timestamps: list[str] | None = None,
    human_summary: str | None = None,
) -> dict[str, Any]:
    return {
        "full_name": repo.get("full_name"),
        "name": repo.get("name"),
        "fork": bool(repo.get("fork")),
        "description": repo.get("description"),
        "language": repo.get("language"),
        "created_at": repo.get("created_at"),
        "pushed_at": repo.get("pushed_at"),
        "latest_commit_message": latest_commits[0] if latest_commits else None,
        "recent_commit_messages": latest_commits or [],
        "readme_summary": readme_summary,
        "changelog_summary": changelog_summary,
        "repo_purpose": repo_purpose,
        "change_summary": change_summary,
        "why_it_matters": why_it_matters,
        "project_context": project_context or [],
        "commit_count": commit_count,
        "top_files": top_files or [],
        "areas_touched": areas_touched or [],
        "change_types": change_types or [],
        "additions": additions,
        "deletions": deletions,
        "patch_snippets": patch_snippets or [],
        "commit_timestamps": commit_timestamps or [],
        "human_summary": human_summary,
    }


def _github_repo_events_for_day(
    user: str,
    run_date: str,
    token: str | None,
    timezone_name: str,
) -> tuple[list[dict[str, Any]], list[str], list[str], list[dict[str, Any]], list[dict[str, Any]]]:
    tz = ZoneInfo(timezone_name)
    day_start_local = datetime.strptime(run_date, "%Y-%m-%d").replace(tzinfo=tz)
    day_end_local = day_start_local + timedelta(days=1)
    day_start_utc = day_start_local.astimezone(timezone.utc)
    day_end_utc = day_end_local.astimezone(timezone.utc)

    created = _fetch_repos(user, "created", token)
    pushed = _fetch_repos(user, "pushed", token)
    repos_by_name: dict[str, dict[str, Any]] = {}
    for repo in created + pushed:
        full_name = str(repo.get("full_name") or "").strip()
        if full_name:
            repos_by_name[full_name] = repo

    events: list[dict[str, Any]] = []
    created_repos: list[str] = []
    updated_repos: list[str] = []
    created_repo_cards: list[dict[str, Any]] = []
    updated_repo_cards: list[dict[str, Any]] = []

    for repo in created:
        created_at = repo.get("created_at")
        if not created_at:
            continue
        t_local = _parse_iso(created_at).astimezone(tz)
        repo_name = repo.get("full_name") or repo.get("name") or "unknown-repo"
        if day_start_local <= t_local < day_end_local:
            created_repos.append(repo_name)
            repo_context = _fetch_repo_context(repo_name, token)
            repo_short_name = str(repo.get("name") or repo_name.split("/")[-1] or "repository")
            repo_purpose = _derive_repo_purpose(
                repo_short_name,
                str(repo.get("description") or ""),
                repo_context.get("readme_summary"),
                list(repo_context.get("project_context") or []),
            )
            change_summary = "It is newly created in this reporting window."
            why_it_matters = "This establishes a new tracked repository in the workspace."
            created_repo_cards.append(
                _repo_card(
                    repo,
                    readme_summary=repo_context.get("readme_summary"),
                    changelog_summary=repo_context.get("changelog_summary"),
                    repo_purpose=repo_purpose,
                    change_summary=change_summary,
                    why_it_matters=why_it_matters,
                    project_context=repo_context.get("project_context"),
                    human_summary=f"The {repo_short_name} repository changed with {repo_purpose}; {change_summary}; {why_it_matters}.",
                )
            )
            events.append(
                {
                    "actor": user,
                    "action": "created repository",
                    "target": repo_name,
                }
            )

    for repo_name, repo in repos_by_name.items():
        commit_refs = _fetch_repo_commits_for_window(repo_name, token, day_start_utc, day_end_utc, limit=20)
        if not commit_refs:
            continue
        updated_repos.append(repo_name)
        repo_context = _fetch_repo_context(repo_name, token)
        commit_details = [
            detail
            for detail in (
                _fetch_commit_detail(repo_name, str((commit_ref.get("sha") or "")).strip(), token)
                for commit_ref in commit_refs
            )
            if detail is not None
        ]
        recent_commits = [
            message
            for message in (
                ((detail.get("commit") or {}).get("message") or "").splitlines()[0].strip()
                for detail in commit_details
            )
            if message
        ]
        commit_timestamps = [
            timestamp
            for timestamp in (_commit_timestamp(commit_ref) for commit_ref in commit_refs)
            if timestamp
        ]
        file_names, additions, deletions = _extract_file_stats(commit_details)
        patch_snippets = _extract_patch_snippets(commit_details, limit=2)
        top_files = _top_items(file_names, 4)
        areas_touched = _top_items([_classify_area(name) for name in file_names], 4)
        change_types = _detect_change_types(recent_commits, file_names)
        repo_short_name = str(repo.get("name") or repo_name.split("/")[-1] or "unknown repository")
        repo_purpose = _derive_repo_purpose(
            repo_short_name,
            str(repo.get("description") or ""),
            repo_context.get("readme_summary"),
            list(repo_context.get("project_context") or []),
        )
        change_summary = _derive_change_summary(
            recent_commits,
            repo_context.get("changelog_summary"),
            top_files,
            areas_touched,
            change_types,
        )
        why_it_matters = _derive_why_it_matters(
            top_files,
            areas_touched,
            change_types,
            additions,
            deletions,
        )
        human_summary = _build_human_summary(
            repo_short_name,
            repo_purpose,
            change_summary,
            why_it_matters,
            repo_context.get("changelog_summary"),
            repo_context.get("readme_summary"),
            list(repo_context.get("project_context") or []),
            recent_commits,
            top_files,
            areas_touched,
            additions,
            deletions,
            patch_snippets,
        )
        updated_repo_cards.append(
            _repo_card(
                repo,
                latest_commits=recent_commits,
                readme_summary=repo_context.get("readme_summary"),
                changelog_summary=repo_context.get("changelog_summary"),
                repo_purpose=repo_purpose,
                change_summary=change_summary,
                why_it_matters=why_it_matters,
                project_context=repo_context.get("project_context"),
                commit_count=len(commit_details),
                top_files=top_files,
                areas_touched=areas_touched,
                change_types=change_types,
                additions=additions,
                deletions=deletions,
                patch_snippets=patch_snippets,
                commit_timestamps=commit_timestamps,
                human_summary=human_summary,
            )
        )
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

    def _dedupe_cards(cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
        unique: list[dict[str, Any]] = []
        seen: set[str] = set()
        for card in cards:
            key = str(card.get("full_name") or card.get("name") or "")
            if not key or key in seen:
                continue
            seen.add(key)
            unique.append(card)
        return unique

    return events, created_unique, updated_unique, _dedupe_cards(created_repo_cards), _dedupe_cards(updated_repo_cards)


def build_outline(
    events: list[dict[str, Any]],
    run_date: str,
    source_name: str,
    story_angle: str,
    timezone_name: str | None = None,
    day_start_local: str | None = None,
    day_end_local: str | None = None,
    day_start_utc: str | None = None,
    day_end_utc: str | None = None,
    created_repos: list[str] | None = None,
    updated_repos: list[str] | None = None,
    created_repo_details: list[dict[str, Any]] | None = None,
    updated_repo_details: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    created_repos = created_repos or []
    updated_repos = updated_repos or []
    created_repo_details = created_repo_details or []
    updated_repo_details = updated_repo_details or []

    top_points: list[str] = []
    top_points.append(f"New repos today: {len(created_repos)}")
    top_points.append(f"Updated repos today: {len(updated_repos)}")
    fork_created = sum(1 for item in created_repo_details if item.get("fork"))
    fork_updated = sum(1 for item in updated_repo_details if item.get("fork"))
    if fork_created:
        top_points.append(f"Forks created today: {fork_created}")
    if fork_updated:
        top_points.append(f"Forks updated today: {fork_updated}")

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
        "timezone": timezone_name,
        "window_local_start": day_start_local,
        "window_local_end": day_end_local,
        "window_utc_start": day_start_utc,
        "window_utc_end": day_end_utc,
        "event_count": len(events),
        "created_count": len(created_repos),
        "updated_count": len(updated_repos),
        "fork_created_count": fork_created,
        "fork_updated_count": fork_updated,
        "created_repos": created_repos,
        "updated_repos": updated_repos,
        "created_repo_details": created_repo_details,
        "updated_repo_details": updated_repo_details,
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
        events, created_repos, updated_repos, created_repo_details, updated_repo_details = _github_repo_events_for_day(
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
        created_repo_details = []
        updated_repo_details = []
        source_name = str(logs_path)

    outline = build_outline(
        events,
        context.run_date,
        source_name,
        story_angle,
        timezone_name=args.timezone if args.source == "github" else None,
        day_start_local=(
            datetime.strptime(context.run_date, "%Y-%m-%d").replace(tzinfo=ZoneInfo(args.timezone)).isoformat()
            if args.source == "github"
            else None
        ),
        day_end_local=(
            (datetime.strptime(context.run_date, "%Y-%m-%d").replace(tzinfo=ZoneInfo(args.timezone)) + timedelta(days=1)).isoformat()
            if args.source == "github"
            else None
        ),
        day_start_utc=(
            datetime.strptime(context.run_date, "%Y-%m-%d").replace(tzinfo=ZoneInfo(args.timezone)).astimezone(timezone.utc).isoformat()
            if args.source == "github"
            else None
        ),
        day_end_utc=(
            (datetime.strptime(context.run_date, "%Y-%m-%d").replace(tzinfo=ZoneInfo(args.timezone)) + timedelta(days=1)).astimezone(timezone.utc).isoformat()
            if args.source == "github"
            else None
        ),
        created_repos=created_repos,
        updated_repos=updated_repos,
        created_repo_details=created_repo_details,
        updated_repo_details=updated_repo_details,
    )

    out_path = context.run_dir / "outline.json"
    out_path.write_text(json.dumps(outline, indent=2), encoding="utf-8")
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
