#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from common import resolve_run_context


def render_blog(outline: dict) -> str:
    date_value = outline.get("date", "unknown-date")
    source = outline.get("source", "unknown-source")
    event_count = outline.get("event_count", 0)
    created_count = outline.get("created_count", 0)
    updated_count = outline.get("updated_count", 0)
    created_repos = outline.get("created_repos", [])
    updated_repos = outline.get("updated_repos", [])
    points = outline.get("top_points", [])
    angle = outline.get("story_angle", "Daily build log")

    point_lines = "\n".join(f"- {point}" for point in points)
    created_lines = "\n".join(f"- {name}" for name in created_repos[:8]) or "- None"
    updated_lines = "\n".join(f"- {name}" for name in updated_repos[:12]) or "- None"

    return f"""# Daily Build Story - {date_value}

## Angle
{angle}

## What Happened
Source: `{source}`  
Parsed events: **{event_count}**
New repos: **{created_count}**  
Updated repos: **{updated_count}**

## New Repositories
{created_lines}

## Updated Repositories
{updated_lines}

{point_lines}

## Narrative Draft
Today was about execution and iteration. The activity stream shows where momentum happened,
where decisions were made, and what deserves follow-up in the next cycle.
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert outline artifact into a daily blog draft.")
    parser.add_argument("--date", dest="run_date", help="Run date in YYYY-MM-DD. Defaults to today.")
    parser.add_argument("--data-dir", default="data", help="Artifact root directory. Default: data")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    context = resolve_run_context(data_dir, args.run_date)

    outline_path = context.run_dir / "outline.json"
    if not outline_path.exists():
        raise FileNotFoundError(f"Missing input: {outline_path}. Run step 01 first.")

    outline = json.loads(outline_path.read_text(encoding="utf-8"))
    blog = render_blog(outline)

    out_path = context.run_dir / "blog.md"
    out_path.write_text(blog, encoding="utf-8")
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
