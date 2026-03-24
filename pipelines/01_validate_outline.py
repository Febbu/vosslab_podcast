#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from common import resolve_run_context
from validators import load_json, validate_outline_payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate outline artifact after step 01.")
    parser.add_argument("--date", dest="run_date", help="Run date in YYYY-MM-DD. Defaults to today.")
    parser.add_argument("--data-dir", default="data", help="Artifact root directory. Default: data")
    args = parser.parse_args()

    context = resolve_run_context(Path(args.data_dir), args.run_date)
    outline_path = context.run_dir / "outline.json"
    if not outline_path.exists():
        raise FileNotFoundError(f"Missing outline artifact: {outline_path}")

    errors = validate_outline_payload(load_json(outline_path))
    if errors:
        raise RuntimeError("Outline validation failed:\n- " + "\n- ".join(errors))
    print(f"Validated {outline_path}")


if __name__ == "__main__":
    main()
