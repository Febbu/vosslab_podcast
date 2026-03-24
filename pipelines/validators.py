from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _repo_key(card: dict[str, Any]) -> str:
    return str(card.get("full_name") or card.get("name") or "").strip()


def validate_outline_payload(outline: dict[str, Any]) -> list[str]:
    errors: list[str] = []

    created_repos = [str(item) for item in outline.get("created_repos", []) if str(item).strip()]
    updated_repos = [str(item) for item in outline.get("updated_repos", []) if str(item).strip()]
    created_cards = [item for item in outline.get("created_repo_details", []) if isinstance(item, dict)]
    updated_cards = [item for item in outline.get("updated_repo_details", []) if isinstance(item, dict)]

    created_count = int(outline.get("created_count", 0))
    updated_count = int(outline.get("updated_count", 0))
    fork_created_count = int(outline.get("fork_created_count", 0))
    fork_updated_count = int(outline.get("fork_updated_count", 0))

    if created_count != len(created_repos):
        errors.append(f"created_count mismatch: {created_count} != len(created_repos)={len(created_repos)}")
    if updated_count != len(updated_repos):
        errors.append(f"updated_count mismatch: {updated_count} != len(updated_repos)={len(updated_repos)}")
    if len(created_cards) != len(created_repos):
        errors.append("created_repo_details length does not match created_repos length")
    if len(updated_cards) != len(updated_repos):
        errors.append("updated_repo_details length does not match updated_repos length")

    created_card_keys = [_repo_key(card) for card in created_cards]
    updated_card_keys = [_repo_key(card) for card in updated_cards]
    if created_card_keys != created_repos:
        errors.append("created_repo_details are not aligned with created_repos")
    if updated_card_keys != updated_repos:
        errors.append("updated_repo_details are not aligned with updated_repos")

    actual_fork_created = sum(1 for card in created_cards if card.get("fork"))
    actual_fork_updated = sum(1 for card in updated_cards if card.get("fork"))
    if fork_created_count != actual_fork_created:
        errors.append(
            f"fork_created_count mismatch: {fork_created_count} != actual fork count {actual_fork_created}"
        )
    if fork_updated_count != actual_fork_updated:
        errors.append(
            f"fork_updated_count mismatch: {fork_updated_count} != actual fork count {actual_fork_updated}"
        )

    for label, cards in (("created", created_cards), ("updated", updated_cards)):
        seen: set[str] = set()
        for card in cards:
            key = _repo_key(card)
            if not key:
                errors.append(f"{label} repo detail missing repo identifier")
                continue
            if key in seen:
                errors.append(f"duplicate {label} repo detail for {key}")
            seen.add(key)
            if not str(card.get("repo_purpose") or "").strip():
                errors.append(f"{label} repo detail missing repo_purpose for {key}")
            if not str(card.get("change_summary") or "").strip():
                errors.append(f"{label} repo detail missing change_summary for {key}")
            if not str(card.get("why_it_matters") or "").strip():
                errors.append(f"{label} repo detail missing why_it_matters for {key}")

    return errors


def validate_script_payload(script: dict[str, Any], outline: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    turns = script.get("turns")
    if not isinstance(turns, list) or not turns:
        return ["script turns are missing or empty"]

    created_count = int(outline.get("created_count", 0))
    updated_count = int(outline.get("updated_count", 0))
    fork_created_count = int(outline.get("fork_created_count", 0))
    fork_updated_count = int(outline.get("fork_updated_count", 0))
    total_activity = created_count + updated_count

    text_blob = "\n".join(str(turn.get("text") or "") for turn in turns).lower()
    quiet_line = "there were no new repositories, updates, or fork changes today."

    if (total_activity + fork_created_count + fork_updated_count) == 0:
        if quiet_line not in text_blob:
            errors.append("quiet day script is missing the quiet-day summary line")
    else:
        if quiet_line in text_blob:
            errors.append("active day script incorrectly uses the quiet-day summary line")

    repo_cards = [
        card
        for key in ("created_repo_details", "updated_repo_details")
        for card in outline.get(key, [])
        if isinstance(card, dict)
    ]
    repo_names = {
        str(card.get("name") or "").strip().lower()
        for card in repo_cards
        if str(card.get("name") or "").strip()
    }
    if total_activity > 0 and repo_names:
        if not any(name in text_blob for name in repo_names):
            errors.append("script does not mention any tracked repository names on an active day")

    repeated_empty_lines = sum(
        1
        for turn in turns
        if "there were no " in str(turn.get("text") or "").lower() or "there was no " in str(turn.get("text") or "").lower()
    )
    if repeated_empty_lines > 2:
        errors.append("script has too many empty-bucket narration lines")

    return errors


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return payload
