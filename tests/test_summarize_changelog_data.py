import json
import os
import sys
import tempfile

import git_file_utils


REPO_ROOT = git_file_utils.get_repo_root()
PIPELINE_DIR = os.path.join(REPO_ROOT, "pipeline")
if PIPELINE_DIR not in sys.path:
	sys.path.insert(0, PIPELINE_DIR)

import summarize_changelog_data


#============================================
def _make_jsonl(records: list[dict], tmp_path: str) -> str:
	"""
	Write records to a temp JSONL file and return the path.
	"""
	path = os.path.join(tmp_path, "test_data.jsonl")
	with open(path, "w", encoding="utf-8") as handle:
		for record in records:
			handle.write(json.dumps(record, ensure_ascii=True) + "\n")
	return path


#============================================
def _read_jsonl(path: str) -> list[dict]:
	"""
	Read all records from a JSONL file.
	"""
	records = []
	with open(path, "r", encoding="utf-8") as handle:
		for raw_line in handle:
			stripped = raw_line.strip()
			if not stripped:
				continue
			records.append(json.loads(stripped))
	return records


#============================================
class FakeClient:
	"""Fake LLM client that returns a fixed summary string."""
	def generate(self, prompt=None, purpose=None, max_tokens=0):
		return "LLM condensed summary."


#============================================
def test_summarize_jsonl_changelogs_replaces_long_entries(tmp_path) -> None:
	"""
	Long repo_changelog latest_entry values should be replaced with LLM summary.
	"""
	records = [
		{"record_type": "run_metadata", "user": "testuser"},
		{
			"record_type": "repo_changelog",
			"repo_full_name": "user/repo1",
			"latest_heading": "## 2026-02-22",
			"latest_entry": "x" * 7000,
			"event_time": "2026-02-22T00:00:00Z",
		},
	]
	path = _make_jsonl(records, str(tmp_path))
	count = summarize_changelog_data.summarize_jsonl_changelogs(
		path, FakeClient(), threshold=6000,
	)
	assert count == 1
	result = _read_jsonl(path)
	# the changelog record should have summarized text
	changelog_rec = [r for r in result if r.get("record_type") == "repo_changelog"][0]
	assert "LLM condensed summary" in changelog_rec["latest_entry"]
	# original long text should be gone
	assert "x" * 100 not in changelog_rec["latest_entry"]


#============================================
def test_summarize_jsonl_changelogs_passthrough_short(tmp_path) -> None:
	"""
	Changelog entries under threshold should pass through unchanged.
	"""
	short_text = "Small changelog update about a bug fix."
	records = [
		{
			"record_type": "repo_changelog",
			"repo_full_name": "user/repo2",
			"latest_heading": "## 2026-02-21",
			"latest_entry": short_text,
			"event_time": "2026-02-21T00:00:00Z",
		},
	]
	path = _make_jsonl(records, str(tmp_path))
	count = summarize_changelog_data.summarize_jsonl_changelogs(
		path, FakeClient(), threshold=6000,
	)
	assert count == 0
	result = _read_jsonl(path)
	assert result[0]["latest_entry"] == short_text


#============================================
def test_summarize_jsonl_changelogs_non_changelog_records_unchanged(tmp_path) -> None:
	"""
	Commit, issue, and metadata records should pass through untouched.
	"""
	records = [
		{"record_type": "run_metadata", "user": "testuser", "window_start": "2026-02-22"},
		{
			"record_type": "commit",
			"repo_full_name": "user/repo3",
			"message": "fix: resolve edge case in parser",
			"event_time": "2026-02-22T10:00:00Z",
		},
		{
			"record_type": "issue",
			"repo_full_name": "user/repo3",
			"title": "Bug in parser",
			"event_time": "2026-02-22T09:00:00Z",
		},
	]
	path = _make_jsonl(records, str(tmp_path))
	count = summarize_changelog_data.summarize_jsonl_changelogs(
		path, FakeClient(), threshold=6000,
	)
	assert count == 0
	result = _read_jsonl(path)
	# all records should be identical to input
	assert len(result) == 3
	assert result[0]["record_type"] == "run_metadata"
	assert result[1]["message"] == "fix: resolve edge case in parser"
	assert result[2]["title"] == "Bug in parser"
