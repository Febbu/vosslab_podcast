#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
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


def _summarize_activity(outline: dict[str, Any] | None, blog_markdown: str) -> tuple[int, int, list[str], list[str]]:
    if outline:
        created_count = int(outline.get("created_count", 0))
        updated_count = int(outline.get("updated_count", 0))
        created_repos = [str(r) for r in outline.get("created_repos", []) if str(r).strip()]
        updated_repos = [str(r) for r in outline.get("updated_repos", []) if str(r).strip()]
        return created_count, updated_count, created_repos, updated_repos

    bullets = _extract_bullets(blog_markdown)
    return 0, 0, [], bullets


def build_script(
    blog_markdown: str,
    run_date: str,
    characters: dict[str, dict[str, str]],
    presenters: int,
    outline: dict[str, Any] | None = None,
) -> dict[str, Any]:
    created_count, updated_count, created_repos, updated_repos = _summarize_activity(outline, blog_markdown)

    host = characters["host"]
    analyst = characters["analyst"]

    new_line = (
        f"Today there were {created_count} new repositories. Highlights: {', '.join(created_repos[:5])}."
        if created_count > 0
        else "There were no new repositories today."
    )
    updated_line = (
        f"There were {updated_count} updated repositories. Highlights: {', '.join(updated_repos[:8])}."
        if updated_count > 0
        else "There were no updated repositories today."
    )

    if presenters == 1:
        turns: list[dict[str, str]] = [
            {
                "role": "HOST",
                "speaker": host["name"],
                "text": (
                    f"Hi, I'm {host['name']}, your host. "
                    f"Welcome to the daily build story for {run_date}."
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
            {
                "role": "HOST",
                "speaker": host["name"],
                "text": "That's the update for today. Next run will continue from this baseline.",
            },
        ]
    else:
        turns = [
            {
                "role": "HOST",
                "speaker": host["name"],
                "text": (
                    f"Hi, I'm {host['name']}, your host. "
                    f"Welcome to the daily build story for {run_date}."
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
            {
                "role": "HOST",
                "speaker": host["name"],
                "text": "That's it for today. We'll continue tomorrow with the next iteration.",
            },
        ]

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
