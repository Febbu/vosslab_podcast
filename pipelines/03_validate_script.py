#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from common import resolve_run_context
from validators import load_json, validate_script_payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate script artifact after step 03.")
    parser.add_argument("--date", dest="run_date", help="Run date in YYYY-MM-DD. Defaults to today.")
    parser.add_argument("--data-dir", default="data", help="Artifact root directory. Default: data")
    args = parser.parse_args()

    context = resolve_run_context(Path(args.data_dir), args.run_date)
    outline_path = context.run_dir / "outline.json"
    script_path = context.run_dir / "script.json"
    if not outline_path.exists():
        raise FileNotFoundError(f"Missing outline artifact: {outline_path}")
    if not script_path.exists():
        raise FileNotFoundError(f"Missing script artifact: {script_path}")

    errors = validate_script_payload(load_json(script_path), load_json(outline_path))
    if errors:
        raise RuntimeError("Script validation failed:\n- " + "\n- ".join(errors))
    print(f"Validated {script_path}")


if __name__ == "__main__":
    main()
