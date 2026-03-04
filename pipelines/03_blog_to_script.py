#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from common import resolve_run_context


def _load_characters(path: Path) -> dict[str, dict[str, str]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("characters config must be a JSON object")
    return payload


def _extract_bullets(blog_markdown: str) -> list[str]:
    bullets: list[str] = []
    for raw in blog_markdown.splitlines():
        line = raw.strip()
        if line.startswith("- "):
            item = line[2:].strip()
            if item.lower() == "none":
                continue
            bullets.append(item)
    return bullets


def _summarize_activity(
    outline: dict[str, Any] | None,
    blog_markdown: str,
) -> tuple[int, int, list[str], list[str], list[dict[str, Any]], list[dict[str, Any]]]:
    if outline:
        created_count = int(outline.get("created_count", 0))
        updated_count = int(outline.get("updated_count", 0))
        created_repos = [str(r) for r in outline.get("created_repos", []) if str(r).strip()]
        updated_repos = [str(r) for r in outline.get("updated_repos", []) if str(r).strip()]
        created_repo_details = [d for d in outline.get("created_repo_details", []) if isinstance(d, dict)]
        updated_repo_details = [d for d in outline.get("updated_repo_details", []) if isinstance(d, dict)]
        return created_count, updated_count, created_repos, updated_repos, created_repo_details, updated_repo_details

    bullets = _extract_bullets(blog_markdown)
    return 0, 0, [], bullets, [], []


def _shorten(text: str | None, max_len: int = 96) -> str:
    cleaned = (text or "").strip()
    if not cleaned:
        return ""
    if len(cleaned) <= max_len:
        return cleaned
    return cleaned[: max_len - 1].rstrip() + "…"


def _ordinal_word(day: int) -> str:
    words = {
        1: "first",
        2: "second",
        3: "third",
        4: "fourth",
        5: "fifth",
        6: "sixth",
        7: "seventh",
        8: "eighth",
        9: "ninth",
        10: "tenth",
        11: "eleventh",
        12: "twelfth",
        13: "thirteenth",
        14: "fourteenth",
        15: "fifteenth",
        16: "sixteenth",
        17: "seventeenth",
        18: "eighteenth",
        19: "nineteenth",
        20: "twentieth",
        21: "twenty first",
        22: "twenty second",
        23: "twenty third",
        24: "twenty fourth",
        25: "twenty fifth",
        26: "twenty sixth",
        27: "twenty seventh",
        28: "twenty eighth",
        29: "twenty ninth",
        30: "thirtieth",
        31: "thirty first",
    }
    return words.get(day, str(day))


def _spoken_date(date_text: str) -> str:
    dt = datetime.strptime(date_text, "%Y-%m-%d")
    return f"{dt.strftime('%B')} {_ordinal_word(dt.day)}, {dt.year}"


def _build_repo_quick_lines(repo_details: list[dict[str, Any]], max_items: int = 2) -> list[str]:
    lines: list[str] = []
    for card in repo_details[:max_items]:
        full_name = str(card.get("full_name") or "").strip()
        short_name = str(card.get("name") or "").strip()
        if short_name:
            display_name = short_name
        elif "/" in full_name:
            display_name = full_name.split("/", 1)[1]
        else:
            display_name = full_name or "unknown repository"
        description = _shorten(str(card.get("description") or ""))
        commit_message = _shorten(str(card.get("latest_commit_message") or ""))
        language = str(card.get("language") or "").strip()

        about_part = f"The {display_name} repository is {description}" if description else f"The {display_name} repository had activity"
        if language:
            about_part += f" ({language})"

        if commit_message:
            line = f"{about_part}. Latest update: {commit_message}."
        else:
            line = f"{about_part}."
        lines.append(line)
    return lines


def build_script(
    blog_markdown: str,
    run_date: str,
    characters: dict[str, dict[str, str]],
    presenters: int,
    outline: dict[str, Any] | None = None,
) -> dict[str, Any]:
    (
        created_count,
        updated_count,
        created_repos,
        updated_repos,
        created_repo_details,
        updated_repo_details,
    ) = _summarize_activity(outline, blog_markdown)

    host = characters["host"]
    analyst = characters["analyst"]
    spoken_date = _spoken_date(run_date)
    created_display = [name.split("/", 1)[1] if "/" in name else name for name in created_repos]
    updated_display = [name.split("/", 1)[1] if "/" in name else name for name in updated_repos]

    new_line = (
        f"Today there were {created_count} new repositories. Highlights: {', '.join(created_display[:5])}."
        if created_count > 0
        else "There were no new repositories today."
    )
    updated_line = (
        f"There were {updated_count} updated repositories. Highlights: {', '.join(updated_display[:8])}."
        if updated_count > 0
        else "There were no updated repositories today."
    )

    repo_quick_lines = _build_repo_quick_lines(updated_repo_details, max_items=3)
    if not repo_quick_lines:
        repo_quick_lines = _build_repo_quick_lines(created_repo_details, max_items=2)
    if not repo_quick_lines and updated_display:
        repo_quick_lines = [f"The {name} repository received updates today." for name in updated_display[:3]]

    if presenters == 1:
        turns: list[dict[str, str]] = [
            {
                "role": "HOST",
                "speaker": host["name"],
                "text": (
                    f"Hi, I'm {host['name']}, your host. "
                    f"Welcome to the daily build story for {spoken_date}."
                ),
            },
            {
                "role": "HOST",
                "speaker": host["name"],
                "text": new_line,
            },
            {
                "role": "HOST",
                "speaker": host["name"],
                "text": updated_line,
            },
        ]
        for detail_line in repo_quick_lines:
            turns.append(
                {
                    "role": "HOST",
                    "speaker": host["name"],
                    "text": detail_line,
                }
            )
        turns.extend(
            [
            {
                "role": "HOST",
                "speaker": host["name"],
                "text": "That's the update for today. I'll be back tomorrow with the next set of repository changes.",
            },
            ]
        )
    else:
        turns = [
            {
                "role": "HOST",
                "speaker": host["name"],
                "text": (
                    f"Hi, I'm {host['name']}, your host. "
                    f"Welcome to the daily build story for {spoken_date}."
                ),
            },
            {
                "role": "ANALYST",
                "speaker": analyst["name"],
                "text": (
                    f"And I'm {analyst['name']}, your analyst. "
                    "I'll break down the technical signals."
                ),
            },
            {
                "role": "HOST",
                "speaker": host["name"],
                "text": new_line,
            },
            {
                "role": "ANALYST",
                "speaker": analyst["name"],
                "text": updated_line,
            },
        ]
        for detail_line in repo_quick_lines:
            turns.append(
                {
                    "role": "ANALYST",
                    "speaker": analyst["name"],
                    "text": detail_line,
                }
            )
        turns.append(
            {
                "role": "HOST",
                "speaker": host["name"],
                "text": "That's it for today. We'll continue tomorrow with the next iteration.",
            }
        )

    return {
        "date": run_date,
        "format_version": 1,
        "presenters": presenters,
        "characters": characters,
        "turns": turns,
    }


def render_script_txt(script_json: dict[str, Any]) -> str:
    lines: list[str] = []
    for turn in script_json["turns"]:
        lines.append(f"{turn['role']}: {turn['text']}")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert blog artifact into a multi-character podcast script.")
    parser.add_argument("--date", dest="run_date", help="Run date in YYYY-MM-DD. Defaults to today.")
    parser.add_argument("--data-dir", default="data", help="Artifact root directory. Default: data")
    parser.add_argument(
        "--characters",
        default="config/characters.json",
        help="Path to character config JSON. Default: config/characters.json",
    )
    parser.add_argument(
        "--presenters",
        type=int,
        choices=[1, 2],
        default=1,
        help="Number of presenters to use (1 or 2). Default: 1",
    )
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    context = resolve_run_context(data_dir, args.run_date)

    blog_path = context.run_dir / "blog.md"
    if not blog_path.exists():
        raise FileNotFoundError(f"Missing input: {blog_path}. Run step 02 first.")

    characters_path = Path(args.characters)
    if not characters_path.exists():
        raise FileNotFoundError(f"Missing characters config: {characters_path}")

    blog = blog_path.read_text(encoding="utf-8")
    characters = _load_characters(characters_path)
    outline_path = context.run_dir / "outline.json"
    outline = None
    if outline_path.exists():
        outline = json.loads(outline_path.read_text(encoding="utf-8"))
    script_json = build_script(blog, context.run_date, characters, presenters=args.presenters, outline=outline)

    script_json_path = context.run_dir / "script.json"
    script_txt_path = context.run_dir / "script.txt"

    script_json_path.write_text(json.dumps(script_json, indent=2), encoding="utf-8")
    script_txt_path.write_text(render_script_txt(script_json), encoding="utf-8")

    print(f"Wrote {script_json_path}")
    print(f"Wrote {script_txt_path}")


if __name__ == "__main__":
    main()
