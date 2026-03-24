#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from common import resolve_run_context
from llm_writer import generate_script_turns, review_script_turns
from validators import validate_script_payload


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
) -> tuple[int, int, int, int, list[str], list[str], list[dict[str, Any]], list[dict[str, Any]]]:
    if outline:
        created_count = int(outline.get("created_count", 0))
        updated_count = int(outline.get("updated_count", 0))
        fork_created_count = int(outline.get("fork_created_count", 0))
        fork_updated_count = int(outline.get("fork_updated_count", 0))
        created_repos = [str(r) for r in outline.get("created_repos", []) if str(r).strip()]
        updated_repos = [str(r) for r in outline.get("updated_repos", []) if str(r).strip()]
        created_repo_details = [d for d in outline.get("created_repo_details", []) if isinstance(d, dict)]
        updated_repo_details = [d for d in outline.get("updated_repo_details", []) if isinstance(d, dict)]
        return (
            created_count,
            updated_count,
            fork_created_count,
            fork_updated_count,
            created_repos,
            updated_repos,
            created_repo_details,
            updated_repo_details,
        )

    bullets = _extract_bullets(blog_markdown)
    return 0, 0, 0, 0, [], bullets, [], []


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
        repo_purpose = _shorten(str(card.get("repo_purpose") or ""), max_len=180)
        change_summary = _shorten(str(card.get("change_summary") or ""), max_len=180)
        why_it_matters = _shorten(str(card.get("why_it_matters") or ""), max_len=160)
        if repo_purpose or change_summary or why_it_matters:
            if card.get("fork"):
                opener = f"The {display_name} fork is about {repo_purpose}" if repo_purpose else f"The {display_name} fork had activity"
            else:
                opener = f"The {display_name} repository is about {repo_purpose}" if repo_purpose else f"The {display_name} repository had activity"
            parts = [opener.rstrip(".") + "."]
            if change_summary:
                parts.append(change_summary.rstrip(".") + ".")
            if why_it_matters:
                parts.append(why_it_matters.rstrip(".") + ".")
            lines.append(" ".join(parts))
            continue
        human_summary = _shorten(str(card.get("human_summary") or ""), max_len=220)
        if human_summary:
            lines.append(human_summary)
            continue
        description = _shorten(str(card.get("description") or ""))
        commit_messages = [
            _shorten(str(message or ""), max_len=72)
            for message in card.get("recent_commit_messages", [])
            if str(message or "").strip()
        ]
        commit_message = _shorten(str(card.get("latest_commit_message") or ""))
        language = str(card.get("language") or "").strip()

        about_part = f"The {display_name} repository is {description}" if description else f"The {display_name} repository had activity"
        if language:
            about_part += f" ({language})"

        if len(commit_messages) >= 2:
            line = f"{about_part}. Recent work included {commit_messages[0]}, and {commit_messages[1]}."
        elif commit_message:
            line = f"{about_part}. Latest update: {commit_message}."
        else:
            line = f"{about_part}."
        lines.append(line)
    return lines


def _split_forks(repo_details: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    originals: list[dict[str, Any]] = []
    forks: list[dict[str, Any]] = []
    for card in repo_details:
        if card.get("fork"):
            forks.append(card)
        else:
            originals.append(card)
    return originals, forks


def _repo_display_names(repo_details: list[dict[str, Any]]) -> list[str]:
    names: list[str] = []
    for card in repo_details:
        short_name = str(card.get("name") or "").strip()
        full_name = str(card.get("full_name") or "").strip()
        if short_name:
            names.append(short_name)
        elif "/" in full_name:
            names.append(full_name.split("/", 1)[1])
    return names


def _activity_line(prefix: str, repo_details: list[dict[str, Any]], empty_text: str) -> str:
    if not repo_details:
        return empty_text
    names = _repo_display_names(repo_details)
    return f"{prefix}: {', '.join(names[:8])}."


def _add_turn(turns: list[dict[str, str]], role: str, speaker: str, text: str | None) -> None:
    cleaned = (text or "").strip()
    if not cleaned:
        return
    turns.append({"role": role, "speaker": speaker, "text": cleaned})


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
        fork_created_count,
        fork_updated_count,
        created_repos,
        updated_repos,
        created_repo_details,
        updated_repo_details,
    ) = _summarize_activity(outline, blog_markdown)

    host = characters["host"]
    analyst = characters["analyst"]
    spoken_date = _spoken_date(run_date)
    created_originals, created_forks = _split_forks(created_repo_details)
    updated_originals, updated_forks = _split_forks(updated_repo_details)

    new_line = _activity_line(
        f"There were {len(created_originals)} new original repositories",
        created_originals,
        "",
    )
    updated_line = _activity_line(
        f"There were {len(updated_originals)} updated original repositories",
        updated_originals,
        "",
    )
    fork_line = (
        f"Fork activity included {fork_created_count} newly created forks and {fork_updated_count} updated forks."
        if (fork_created_count or fork_updated_count)
        else ""
    )
    new_fork_line = _activity_line(
        f"New forked repositories totaled {len(created_forks)}",
        created_forks,
        "",
    )
    updated_fork_line = _activity_line(
        f"Updated forks totaled {len(updated_forks)}",
        updated_forks,
        "",
    )
    if not any([new_line, updated_line, fork_line, new_fork_line, updated_fork_line]):
        quiet_day_line = "There were no new repositories, updates, or fork changes today."
    else:
        quiet_day_line = ""

    repo_quick_lines: list[str] = []
    repo_quick_lines.extend(_build_repo_quick_lines(created_originals, max_items=len(created_originals)))
    repo_quick_lines.extend(_build_repo_quick_lines(updated_originals, max_items=len(updated_originals)))
    repo_quick_lines.extend(_build_repo_quick_lines(created_forks, max_items=len(created_forks)))
    repo_quick_lines.extend(_build_repo_quick_lines(updated_forks, max_items=len(updated_forks)))

    if presenters == 1:
        turns: list[dict[str, str]] = []
        _add_turn(
            turns,
            "HOST",
            host["name"],
            f"Hi, I'm {host['name']}, your host. Welcome to the daily build story for {spoken_date}.",
        )
        _add_turn(turns, "HOST", host["name"], quiet_day_line or new_line)
        _add_turn(turns, "HOST", host["name"], updated_line if not quiet_day_line else "")
        _add_turn(turns, "HOST", host["name"], fork_line if not quiet_day_line else "")
        _add_turn(turns, "HOST", host["name"], new_fork_line if not quiet_day_line else "")
        _add_turn(turns, "HOST", host["name"], updated_fork_line if not quiet_day_line else "")
        for detail_line in repo_quick_lines:
            _add_turn(turns, "HOST", host["name"], detail_line if not quiet_day_line else "")
        _add_turn(
            turns,
            "HOST",
            host["name"],
            "That's the update for today. I'll be back tomorrow with the next set of repository changes.",
        )
    else:
        turns = []
        _add_turn(
            turns,
            "HOST",
            host["name"],
            f"Hi, I'm {host['name']}, your host. Welcome to the daily build story for {spoken_date}.",
        )
        _add_turn(
            turns,
            "ANALYST",
            analyst["name"],
            f"And I'm {analyst['name']}, your analyst. I'll break down the technical signals.",
        )
        _add_turn(turns, "HOST", host["name"], quiet_day_line or new_line)
        _add_turn(turns, "ANALYST", analyst["name"], updated_line if not quiet_day_line else "")
        _add_turn(turns, "HOST", host["name"], fork_line if not quiet_day_line else "")
        _add_turn(turns, "ANALYST", analyst["name"], new_fork_line if not quiet_day_line else "")
        _add_turn(turns, "ANALYST", analyst["name"], updated_fork_line if not quiet_day_line else "")
        for detail_line in repo_quick_lines:
            _add_turn(turns, "ANALYST", analyst["name"], detail_line if not quiet_day_line else "")
        _add_turn(
            turns,
            "HOST",
            host["name"],
            "That's it for today. We'll continue tomorrow with the next iteration.",
        )

    return {
        "date": run_date,
        "format_version": 1,
        "presenters": presenters,
        "characters": characters,
        "turns": turns,
    }


def build_script_with_writer(
    *,
    blog_markdown: str,
    run_date: str,
    characters: dict[str, dict[str, str]],
    presenters: int,
    outline: dict[str, Any] | None,
    writer: str,
    llm_transport: str,
    llm_model: str | None,
    llm_max_tokens: int,
    referee: str,
    referee_transport: str,
    referee_model: str | None,
    referee_max_tokens: int,
) -> dict[str, Any]:
    deterministic = build_script(
        blog_markdown,
        run_date,
        characters,
        presenters,
        outline=outline,
    )
    if writer != "llm" or outline is None:
        return deterministic

    host = characters["host"]
    analyst = characters["analyst"]
    spoken_date = _spoken_date(run_date)

    def _as_script(turns: list[dict[str, str]]) -> dict[str, Any]:
        role_to_speaker = {
            "HOST": host["name"],
            "ANALYST": analyst["name"],
        }
        script = dict(deterministic)
        script["turns"] = [
            {
                "role": turn["role"],
                "speaker": role_to_speaker.get(turn["role"], turn["role"]),
                "text": turn["text"],
            }
            for turn in turns
        ]
        script["writer"] = "llm"
        return script

    try:
        llm_turns = generate_script_turns(
            outline=outline,
            host=host,
            analyst=analyst,
            presenters=presenters,
            spoken_date=spoken_date,
            transport_name=llm_transport,
            model_override=llm_model,
            max_tokens=llm_max_tokens,
            quiet=True,
        )
    except Exception as error:
        print(f"[03_blog_to_script] LLM writer failed, falling back to deterministic script: {error}")
        return deterministic

    if not llm_turns:
        print("[03_blog_to_script] LLM writer returned no usable speaker lines, falling back to deterministic script.")
        return deterministic
    llm_script = _as_script(llm_turns)

    deterministic_errors = validate_script_payload(llm_script, outline)
    if deterministic_errors:
        print("[03_blog_to_script] LLM script failed deterministic validation, falling back to deterministic script:")
        for error in deterministic_errors:
            print(f"  - {error}")
        return deterministic

    if referee == "llm":
        try:
            verdict, feedback = review_script_turns(
                outline=outline,
                script_text=render_script_txt(llm_script),
                transport_name=referee_transport,
                model_override=referee_model,
                max_tokens=referee_max_tokens,
                quiet=True,
            )
        except Exception as error:
            print(f"[03_blog_to_script] LLM referee failed, keeping first LLM script: {error}")
            verdict, feedback = True, []
        if not verdict:
            print("[03_blog_to_script] LLM referee requested one rewrite pass.")
            try:
                rewritten_turns = generate_script_turns(
                    outline=outline,
                    host=host,
                    analyst=analyst,
                    presenters=presenters,
                    spoken_date=spoken_date,
                    transport_name=llm_transport,
                    model_override=llm_model,
                    max_tokens=llm_max_tokens,
                    quiet=True,
                    feedback="\n".join(feedback),
                )
                if rewritten_turns:
                    rewritten_script = _as_script(rewritten_turns)
                    rewritten_errors = validate_script_payload(rewritten_script, outline)
                    if not rewritten_errors:
                        llm_script = rewritten_script
                    else:
                        print("[03_blog_to_script] Rewritten LLM script failed deterministic validation; keeping first LLM script.")
            except Exception as error:
                print(f"[03_blog_to_script] Rewrite after referee feedback failed: {error}")

    return llm_script


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
    parser.add_argument(
        "--writer",
        choices=["deterministic", "llm"],
        default="deterministic",
        help="Script writer mode. Default: deterministic",
    )
    parser.add_argument(
        "--llm-transport",
        choices=["apple", "ollama", "auto"],
        default="auto",
        help="Local LLM transport when --writer llm. Default: auto",
    )
    parser.add_argument(
        "--llm-model",
        default=None,
        help="Optional local LLM model override when --writer llm.",
    )
    parser.add_argument(
        "--llm-max-tokens",
        type=int,
        default=900,
        help="Maximum local LLM generation tokens when --writer llm. Default: 900",
    )
    parser.add_argument(
        "--referee",
        choices=["none", "llm"],
        default="none",
        help="Optional referee mode for Step 3. Default: none",
    )
    parser.add_argument(
        "--referee-transport",
        choices=["apple", "ollama", "auto"],
        default="auto",
        help="Local LLM transport when --referee llm. Default: auto",
    )
    parser.add_argument(
        "--referee-model",
        default=None,
        help="Optional local LLM model override when --referee llm.",
    )
    parser.add_argument(
        "--referee-max-tokens",
        type=int,
        default=500,
        help="Maximum local LLM generation tokens when --referee llm. Default: 500",
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
    script_json = build_script_with_writer(
        blog_markdown=blog,
        run_date=context.run_date,
        characters=characters,
        presenters=args.presenters,
        outline=outline,
        writer=args.writer,
        llm_transport=args.llm_transport,
        llm_model=args.llm_model,
        llm_max_tokens=args.llm_max_tokens,
        referee=args.referee,
        referee_transport=args.referee_transport,
        referee_model=args.referee_model,
        referee_max_tokens=args.referee_max_tokens,
    )

    script_json_path = context.run_dir / "script.json"
    script_txt_path = context.run_dir / "script.txt"

    script_json_path.write_text(json.dumps(script_json, indent=2), encoding="utf-8")
    script_txt_path.write_text(render_script_txt(script_json), encoding="utf-8")

    print(f"Wrote {script_json_path}")
    print(f"Wrote {script_txt_path}")


if __name__ == "__main__":
    main()
