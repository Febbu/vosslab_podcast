import json
import os
import sys

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
	cache_dir = os.path.join(str(tmp_path), "depth_cache")
	count = summarize_changelog_data.summarize_jsonl_changelogs(
		path, FakeClient(), threshold=6000,
		depth=1, cache_dir=cache_dir, continue_mode=True, max_tokens=1024,
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
	cache_dir = os.path.join(str(tmp_path), "depth_cache")
	count = summarize_changelog_data.summarize_jsonl_changelogs(
		path, FakeClient(), threshold=6000,
		depth=1, cache_dir=cache_dir, continue_mode=True, max_tokens=1024,
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
	cache_dir = os.path.join(str(tmp_path), "depth_cache")
	count = summarize_changelog_data.summarize_jsonl_changelogs(
		path, FakeClient(), threshold=6000,
		depth=1, cache_dir=cache_dir, continue_mode=True, max_tokens=1024,
	)
	assert count == 0
	result = _read_jsonl(path)
	# all records should be identical to input
	assert len(result) == 3
	assert result[0]["record_type"] == "run_metadata"
	assert result[1]["message"] == "fix: resolve edge case in parser"
	assert result[2]["title"] == "Bug in parser"


#============================================
def test_summarize_jsonl_changelogs_depth2_uses_pipeline(tmp_path) -> None:
	"""
	At depth 2, the pipeline should generate multiple drafts and polish.
	"""
	draft_count = [0]

	class DepthFakeClient:
		"""Fake LLM client that tracks draft generation and polish calls."""
		def generate(self, prompt=None, purpose=None, max_tokens=0):
			# track draft generation calls (chunk summaries)
			if "chunk" in (purpose or ""):
				draft_count[0] += 1
				return f"Chunk summary {draft_count[0]}."
			# polish call returns a polished result
			if "polish" in (purpose or ""):
				return "Polished changelog summary."
			# default fallback
			return "Draft summary text."

	records = [
		{
			"record_type": "repo_changelog",
			"repo_full_name": "user/depthrepo",
			"latest_heading": "## 2026-02-22",
			"latest_entry": "z" * 7000,
			"event_time": "2026-02-22T00:00:00Z",
		},
	]
	path = _make_jsonl(records, str(tmp_path))
	cache_dir = os.path.join(str(tmp_path), "depth_cache")
	count = summarize_changelog_data.summarize_jsonl_changelogs(
		path, DepthFakeClient(), threshold=6000,
		depth=2, cache_dir=cache_dir, continue_mode=False, max_tokens=1024,
	)
	assert count == 1
	# at depth 2, should have generated multiple drafts (each with chunk calls)
	# each draft requires multiple chunk summary calls for 7000 chars
	assert draft_count[0] >= 4
	result = _read_jsonl(path)
	changelog_rec = [r for r in result if r.get("record_type") == "repo_changelog"][0]
	# the polished result should be in the output
	assert "summary" in changelog_rec["latest_entry"].lower()


#============================================
def test_changelog_summary_quality_issue() -> None:
	"""
	Quality check should return empty for good text, non-empty for bad.
	"""
	# good text returns empty string
	assert summarize_changelog_data._changelog_summary_quality_issue("Good summary.") == ""
	# empty text returns issue
	assert summarize_changelog_data._changelog_summary_quality_issue("") != ""
	assert summarize_changelog_data._changelog_summary_quality_issue(None) != ""
	# error payload returns issue
	assert summarize_changelog_data._changelog_summary_quality_issue(
		'{"error_code": "500"}'
	) != ""
	# structured error object returns issue
	assert summarize_changelog_data._changelog_summary_quality_issue(
		'{"some": "json"}'
	) != ""
	# generationerror returns issue
	assert summarize_changelog_data._changelog_summary_quality_issue(
		"GenerationError: model failed"
	) != ""
