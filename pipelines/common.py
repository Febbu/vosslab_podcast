from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path


@dataclass(frozen=True)
class RunContext:
    run_date: str
    run_dir: Path


def resolve_run_context(base_dir: Path, run_date: str | None = None) -> RunContext:
    if run_date:
        normalized = run_date
    else:
        normalized = date.today().isoformat()

    # Validate date format early for safer path handling.
    datetime.strptime(normalized, "%Y-%m-%d")

    run_dir = base_dir / normalized
    run_dir.mkdir(parents=True, exist_ok=True)
    return RunContext(run_date=normalized, run_dir=run_dir)
