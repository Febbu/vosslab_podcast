from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any


SPEAKER_LINE_RE = re.compile(r"^\s*([A-Za-z0-9_ -]+)\s*:\s*(.+?)\s*$")
XML_TAGS = ("response", "output", "podcast_script", "content")


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def add_local_llm_wrapper_to_path() -> None:
    wrapper_root = _repo_root() / "local-llm-wrapper"
    if wrapper_root.is_dir():
        wrapper_text = str(wrapper_root)
        if wrapper_text not in sys.path:
            sys.path.insert(0, wrapper_text)


def create_llm_client(transport_name: str, model_override: str | None, quiet: bool) -> object:
    add_local_llm_wrapper_to_path()
    import local_llm_wrapper.llm as llm

    model_choice = llm.choose_model(model_override or None)
    transports = []
    if transport_name == "ollama":
        transports.append(llm.OllamaTransport(model=model_choice))
    elif transport_name == "apple":
        transports.append(llm.AppleTransport())
    elif transport_name == "auto":
        transports.append(llm.AppleTransport())
        transports.append(llm.OllamaTransport(model=model_choice))
    else:
        raise RuntimeError(f"Unsupported llm transport: {transport_name}")
    return llm.LLMClient(transports=transports, quiet=quiet)


def strip_xml_wrapper(raw_text: str) -> str:
    cleaned = raw_text.strip()
    for tag in XML_TAGS:
        pattern = rf"<{tag}>(.*?)</{tag}>"
        match = re.search(pattern, cleaned, flags=re.DOTALL | re.IGNORECASE)
        if match:
            candidate = match.group(1).strip()
            if candidate:
                return candidate
    return cleaned


def _load_prompt_template(name: str) -> str:
    path = Path(__file__).resolve().parent / "prompts" / name
    return path.read_text(encoding="utf-8")


def _render_prompt(template: str, values: dict[str, str]) -> str:
    rendered = template
    for key, value in values.items():
        rendered = rendered.replace("{{" + key + "}}", value)
    return rendered


def _bucket_lines(label: str, repo_cards: list[dict[str, Any]]) -> list[str]:
    if not repo_cards:
        return []
    lines = [f"{label} ({len(repo_cards)}):"]
    for card in repo_cards:
        name = str(card.get("name") or card.get("full_name") or "unknown repository").strip()
        if "/" in name:
            name = name.split("/", 1)[1]
        summary = str(card.get("human_summary") or "").strip()
        if not summary:
            summary = str(card.get("description") or "no summary available").strip()
        lines.append(f"- {name}: {summary}")
    return lines


def build_activity_summary(outline: dict[str, Any]) -> str:
    created_cards = [card for card in outline.get("created_repo_details", []) if isinstance(card, dict)]
    updated_cards = [card for card in outline.get("updated_repo_details", []) if isinstance(card, dict)]
    created_originals = [card for card in created_cards if not card.get("fork")]
    created_forks = [card for card in created_cards if card.get("fork")]
    updated_originals = [card for card in updated_cards if not card.get("fork")]
    updated_forks = [card for card in updated_cards if card.get("fork")]

    parts = [
        f"Date: {outline.get('date', '')}",
        f"New original repositories: {len(created_originals)}",
        f"Updated original repositories: {len(updated_originals)}",
        f"New forks: {len(created_forks)}",
        f"Updated forks: {len(updated_forks)}",
    ]
    for label, cards in (
        ("New original repositories", created_originals),
        ("Updated original repositories", updated_originals),
        ("Newly created forks", created_forks),
        ("Updated forks", updated_forks),
    ):
        parts.extend(_bucket_lines(label, cards))
    return "\n".join(parts).strip()


def _normalize_speaker(token: str) -> str:
    return token.strip().upper().replace(" ", "_")


def parse_script_lines(raw_text: str, allowed_roles: list[str]) -> list[dict[str, str]]:
    parsed: list[dict[str, str]] = []
    allowed = {role.upper() for role in allowed_roles}
    for raw_line in raw_text.splitlines():
        match = SPEAKER_LINE_RE.match(raw_line)
        if not match:
            continue
        role = _normalize_speaker(match.group(1))
        text = match.group(2).strip()
        if role in allowed and text:
            parsed.append({"role": role, "text": text})
    return parsed


def generate_script_turns(
    *,
    outline: dict[str, Any],
    host: dict[str, str],
    analyst: dict[str, str],
    presenters: int,
    spoken_date: str,
    transport_name: str,
    model_override: str | None,
    max_tokens: int,
    quiet: bool,
    feedback: str | None = None,
) -> list[dict[str, str]]:
    template = _load_prompt_template("script_writer.txt")
    roles = ["HOST"] if presenters == 1 else ["HOST", "ANALYST"]
    speaker_format = "\n".join(f"- {role}: one spoken sentence or two" for role in roles)
    prompt_values = {
        "host_name": host["name"],
        "host_bio": host.get("bio", ""),
        "analyst_name": analyst["name"],
        "analyst_bio": analyst.get("bio", ""),
        "speaker_format": speaker_format,
        "spoken_date": spoken_date,
        "activity_summary": build_activity_summary(outline),
    }
    prompt = _render_prompt(
        template,
        prompt_values,
    )
    if feedback:
        prompt += "\n\nRevision feedback:\n" + feedback.strip() + "\nPlease fix these issues."
    client = create_llm_client(transport_name, model_override, quiet)
    raw_text = client.generate(prompt=prompt, purpose="daily repo podcast script", max_tokens=max_tokens)
    raw_text = strip_xml_wrapper(raw_text)
    return parse_script_lines(raw_text, roles)


def review_script_turns(
    *,
    outline: dict[str, Any],
    script_text: str,
    transport_name: str,
    model_override: str | None,
    max_tokens: int,
    quiet: bool,
) -> tuple[bool, list[str]]:
    template = _load_prompt_template("script_referee.txt")
    prompt = _render_prompt(
        template,
        {
            "activity_summary": build_activity_summary(outline),
            "script_text": script_text.strip(),
        },
    )
    client = create_llm_client(transport_name, model_override, quiet)
    raw_text = client.generate(prompt=prompt, purpose="podcast script referee", max_tokens=max_tokens)
    raw_text = strip_xml_wrapper(raw_text)
    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    if not lines:
        return False, ["LLM referee returned no output."]
    verdict = lines[0].upper() == "PASS"
    feedback = [line[2:].strip() if line.startswith("- ") else line for line in lines[1:5]]
    feedback = [line for line in feedback if line]
    return verdict, feedback
