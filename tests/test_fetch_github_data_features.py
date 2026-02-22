import argparse
import json
import os
import sys
from datetime import datetime
from datetime import timedelta
from datetime import timezone

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
def test_compute_completed_window_local_examples() -> None:
	"""
	Last-day window should be the most recent fully completed 5am->5am local period.
	"""
	tz = timezone(timedelta(hours=-5))
	start_one, end_one = fetch_github_data.compute_completed_window_local(
		1,
		datetime(2026, 2, 22, 8, 0, tzinfo=tz),
	)
	assert start_one.isoformat() == "2026-02-21T05:00:00-05:00"
	assert end_one.isoformat() == "2026-02-22T05:00:00-05:00"

	start_two, end_two = fetch_github_data.compute_completed_window_local(
		1,
		datetime(2026, 2, 22, 20, 0, tzinfo=tz),
	)
	assert start_two.isoformat() == "2026-02-21T05:00:00-05:00"
	assert end_two.isoformat() == "2026-02-22T05:00:00-05:00"

	start_three, end_three = fetch_github_data.compute_completed_window_local(
		1,
		datetime(2026, 2, 23, 4, 0, tzinfo=tz),
	)
	assert start_three.isoformat() == "2026-02-21T05:00:00-05:00"
	assert end_three.isoformat() == "2026-02-22T05:00:00-05:00"


#============================================
def test_build_window_day_keys_from_window_start() -> None:
	"""
	Day keys should begin at local window start date for completed windows.
	"""
	window_start = fetch_github_data.parse_iso("2026-02-21T10:00:00+00:00")
	keys = fetch_github_data.build_window_day_keys(window_start, 3)
	assert keys == ["2026-02-21", "2026-02-22", "2026-02-23"]


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


#============================================
def test_repo_list_cache_round_trip(tmp_path, monkeypatch) -> None:
	"""
	Repo list cache should save and load within 24-hour TTL.
	"""
	monkeypatch.chdir(tmp_path)
	now = fetch_github_data.parse_iso("2026-02-22T12:00:00+00:00")
	repos = [{"full_name": "vosslab/example", "name": "example"}]
	cache_path = fetch_github_data.save_repo_list_cache("vosslab", now, repos)
	assert os.path.isfile(cache_path)
	loaded = fetch_github_data.load_repo_list_cache("vosslab", now + timedelta(hours=1))
	assert loaded == repos


#============================================
def test_repo_list_cache_expires_after_24_hours(tmp_path, monkeypatch) -> None:
	"""
	Repo list cache should expire when older than 24 hours.
	"""
	monkeypatch.chdir(tmp_path)
	now = fetch_github_data.parse_iso("2026-02-22T12:00:00+00:00")
	repos = [{"full_name": "vosslab/example2", "name": "example2"}]
	fetch_github_data.save_repo_list_cache("vosslab", now, repos)
	expired = fetch_github_data.load_repo_list_cache("vosslab", now + timedelta(hours=25))
	assert expired == []


#============================================
def test_repo_list_cache_allows_stale_when_requested(tmp_path, monkeypatch) -> None:
	"""
	Repo list cache should load stale entries when max age is disabled.
	"""
	monkeypatch.chdir(tmp_path)
	now = fetch_github_data.parse_iso("2026-02-22T12:00:00+00:00")
	repos = [{"full_name": "vosslab/example3", "name": "example3"}]
	fetch_github_data.save_repo_list_cache("vosslab", now, repos)
	stale_loaded = fetch_github_data.load_repo_list_cache(
		"vosslab",
		now + timedelta(days=3),
		max_age_seconds=None,
	)
	assert stale_loaded == repos
