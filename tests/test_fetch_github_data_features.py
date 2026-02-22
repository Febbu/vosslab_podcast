import argparse
import json
import os
import sys

import git_file_utils


REPO_ROOT = git_file_utils.get_repo_root()
PIPELINE_DIR = os.path.join(REPO_ROOT, "pipeline")
if PIPELINE_DIR not in sys.path:
	sys.path.insert(0, PIPELINE_DIR)

import fetch_github_data


#============================================
def make_args(**kwargs) -> argparse.Namespace:
	"""
	Build a namespace compatible with resolve_window_days.
	"""
	defaults = {
		"last_day": False,
		"last_week": False,
		"last_month": False,
	}
	defaults.update(kwargs)
	return argparse.Namespace(**defaults)


#============================================
def test_resolve_window_days_default_last_day() -> None:
	"""
	Default selection should resolve to one day.
	"""
	args = make_args()
	assert fetch_github_data.resolve_window_days(args) == 1


#============================================
def test_resolve_window_days_last_week() -> None:
	"""
	Last week flag should resolve to 7 days.
	"""
	assert fetch_github_data.resolve_window_days(make_args(last_week=True)) == 7


#============================================
def test_resolve_window_days_last_month() -> None:
	"""
	Last month flag should resolve to 30 days.
	"""
	assert fetch_github_data.resolve_window_days(make_args(last_month=True)) == 30


#============================================
def test_parse_latest_changelog_entry() -> None:
	"""
	Latest dated changelog section should be extracted from markdown text.
	"""
	text = (
		"# Changelog\n\n"
		"## 2026-02-22\n"
		"- Patch 1\n"
		"- Patch 2\n\n"
		"## 2026-02-21\n"
		"- Older patch\n"
	)
	heading, date_value, entry_text = fetch_github_data.parse_latest_changelog_entry(text)
	assert heading == "## 2026-02-22"
	assert date_value == "2026-02-22"
	assert "- Patch 2" in entry_text


#============================================
def test_write_daily_cache_files(tmp_path) -> None:
	"""
	Daily cache writer should emit one JSONL file per day key.
	"""
	day_keys = ["2026-02-21", "2026-02-22"]
	daily_buckets = {
		"2026-02-22": [
			{
				"record_type": "commit",
				"event_time": "2026-02-22T10:30:00+00:00",
				"repo_full_name": "vosslab/repo_one",
			}
		]
	}
	written = fetch_github_data.write_daily_cache_files(
		str(tmp_path),
		"vosslab",
		fetch_github_data.parse_iso("2026-02-21T00:00:00+00:00"),
		fetch_github_data.parse_iso("2026-02-22T23:59:59+00:00"),
		day_keys,
		daily_buckets,
	)
	assert len(written) == 2
	day_one = tmp_path / "github_data_2026-02-21.jsonl"
	day_two = tmp_path / "github_data_2026-02-22.jsonl"
	assert day_one.is_file()
	assert day_two.is_file()

	lines = day_two.read_text(encoding="utf-8").strip().splitlines()
	assert len(lines) == 3
	summary = json.loads(lines[-1])
	assert summary["record_type"] == "daily_summary"
	assert summary["total_records"] == 1
