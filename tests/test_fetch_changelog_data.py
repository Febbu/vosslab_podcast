"""Unit tests for multi-date changelog parsing in fetch_github_data."""

# Standard Library
import sys

# local repo modules
import git_file_utils

REPO_ROOT = git_file_utils.get_repo_root()
sys.path.insert(0, REPO_ROOT)

import pipeline.fetch_github_data as fetch_mod


MULTI_DAY_CHANGELOG = """\
# Changelog

## 2026-02-22

### Additions and New Features
- Added feature A

### Fixes and Maintenance
- Fixed bug B

## 2026-02-21

### Additions and New Features
- Added feature C

## 2026-02-19

### Fixes and Maintenance
- Fixed bug D
"""

SINGLE_DAY_CHANGELOG = """\
## 2026-02-22

### Additions and New Features
- Added feature A
"""


#============================================
def test_parse_all_changelog_entries_multi():
	"""Multi-day changelog returns all sections."""
	results = fetch_mod.parse_all_changelog_entries(MULTI_DAY_CHANGELOG)
	assert len(results) == 3
	# check dates in order
	dates = [entry[1] for entry in results]
	assert dates == ["2026-02-22", "2026-02-21", "2026-02-19"]
	# check heading values
	assert results[0][0] == "## 2026-02-22"
	assert results[1][0] == "## 2026-02-21"
	assert results[2][0] == "## 2026-02-19"
	# check entry text contains content
	assert "Added feature A" in results[0][2]
	assert "Fixed bug B" in results[0][2]
	assert "Added feature C" in results[1][2]
	assert "Fixed bug D" in results[2][2]


#============================================
def test_parse_all_changelog_entries_single():
	"""Single-day changelog returns list of one."""
	results = fetch_mod.parse_all_changelog_entries(SINGLE_DAY_CHANGELOG)
	assert len(results) == 1
	assert results[0][1] == "2026-02-22"
	assert "Added feature A" in results[0][2]


#============================================
def test_parse_all_changelog_entries_empty():
	"""Empty string returns empty list."""
	assert fetch_mod.parse_all_changelog_entries("") == []
	assert fetch_mod.parse_all_changelog_entries("   ") == []
	assert fetch_mod.parse_all_changelog_entries("# No date headings here\n") == []


#============================================
def test_strip_changelog_noise_links_and_paths():
	"""Markdown links become plain text, backticked paths become basenames."""
	text = "- Added [docs/FILE.md](docs/FILE.md) with `pipeline/podlib/audio_utils.py` helper"
	result = fetch_mod.strip_changelog_noise(text)
	# markdown link replaced with link text
	assert "docs/FILE.md" in result
	assert "](docs/FILE.md)" not in result
	# backticked path replaced with basename
	assert "audio_utils.py" in result
	assert "pipeline/podlib/" not in result


#============================================
def test_build_changelog_records_filters_by_window():
	"""Only entries whose UTC date falls within the window are included."""
	from datetime import datetime, timezone
	# window spans UTC dates 2026-02-21 and 2026-02-22
	window_start = datetime(2026, 2, 21, tzinfo=timezone.utc)
	window_end = datetime(2026, 2, 22, tzinfo=timezone.utc)
	changelog_info = {
		"path": "docs/CHANGELOG.md",
		"sha": "abc123",
		"size": 500,
		"changelog_text": MULTI_DAY_CHANGELOG,
	}
	records = fetch_mod.build_changelog_records(
		"testuser", window_start, window_end,
		"owner/repo", "repo", changelog_info,
	)
	assert len(records) == 2
	record_dates = [r["event_time"] for r in records]
	assert "2026-02-22T12:00:00+00:00" in record_dates
	assert "2026-02-21T12:00:00+00:00" in record_dates
	# 2026-02-19 is outside the window
	assert "2026-02-19T12:00:00+00:00" not in record_dates
	# verify record fields
	for record in records:
		assert record["record_type"] == "repo_changelog"
		assert record["user"] == "testuser"
		assert record["repo_full_name"] == "owner/repo"
		assert record["repo_name"] == "repo"
		assert record["path"] == "docs/CHANGELOG.md"
		assert record["sha"] == "abc123"


#============================================
def test_build_changelog_records_window_spans_utc_dates():
	"""Window start/end on different UTC dates captures both."""
	from datetime import datetime, timezone
	# window from Feb 20 11:00 to Feb 21 11:00 spans UTC dates 20, 21
	window_start = datetime(2026, 2, 20, 11, 0, 0, tzinfo=timezone.utc)
	window_end = datetime(2026, 2, 21, 11, 0, 0, tzinfo=timezone.utc)
	changelog_info = {
		"path": "docs/CHANGELOG.md",
		"sha": "abc123",
		"size": 500,
		"changelog_text": MULTI_DAY_CHANGELOG,
	}
	records = fetch_mod.build_changelog_records(
		"testuser", window_start, window_end,
		"owner/repo", "repo", changelog_info,
	)
	record_dates = [r["event_time"][:10] for r in records]
	# both 2026-02-20 and 2026-02-21 are UTC dates in the window
	assert "2026-02-21" in record_dates
	assert "2026-02-19" not in record_dates


#============================================
def test_build_changelog_records_no_match():
	"""No entries match window returns empty list."""
	from datetime import datetime, timezone
	# window in January does not overlap any changelog dates
	window_start = datetime(2026, 1, 1, tzinfo=timezone.utc)
	window_end = datetime(2026, 1, 7, tzinfo=timezone.utc)
	changelog_info = {
		"path": "docs/CHANGELOG.md",
		"sha": "abc123",
		"size": 500,
		"changelog_text": MULTI_DAY_CHANGELOG,
	}
	records = fetch_mod.build_changelog_records(
		"testuser", window_start, window_end,
		"owner/repo", "repo", changelog_info,
	)
	assert len(records) == 0
