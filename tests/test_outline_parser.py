import json
import os
import sys

import git_file_utils


REPO_ROOT = git_file_utils.get_repo_root()
PIPELINE_DIR = os.path.join(REPO_ROOT, "pipeline")
if PIPELINE_DIR not in sys.path:
	sys.path.insert(0, PIPELINE_DIR)

import github_data_to_outline


#============================================
def write_jsonl(path: str, records: list[dict]) -> None:
	"""
	Write records to JSONL for parser tests.
	"""
	with open(path, "w", encoding="utf-8") as handle:
		for record in records:
			handle.write(json.dumps(record))
			handle.write("\n")


#============================================
def test_parse_jsonl_to_outline(tmp_path) -> None:
	"""
	Ensure parser aggregates repo, commit, issue, and pull request records.
	"""
	jsonl_path = tmp_path / "github_data.jsonl"
	records = [
		{
			"record_type": "run_metadata",
			"user": "vosslab",
			"window_start": "2026-02-15T00:00:00+00:00",
			"window_end": "2026-02-22T00:00:00+00:00",
		},
		{
			"record_type": "repo",
			"user": "vosslab",
			"repo_full_name": "vosslab/alpha_repo",
			"repo_name": "alpha_repo",
			"event_time": "2026-02-21T12:00:00+00:00",
			"data": {
				"name": "alpha_repo",
				"html_url": "https://github.com/vosslab/alpha_repo",
				"description": "alpha description",
				"language": "Python",
			},
		},
		{
			"record_type": "commit",
			"user": "vosslab",
			"repo_full_name": "vosslab/alpha_repo",
			"repo_name": "alpha_repo",
			"event_time": "2026-02-21T13:00:00+00:00",
			"message": "add parser stage\n\nextra details",
		},
		{
			"record_type": "issue",
			"user": "vosslab",
			"repo_full_name": "vosslab/alpha_repo",
			"repo_name": "alpha_repo",
			"event_time": "2026-02-21T14:00:00+00:00",
			"title": "tracking issue",
		},
		{
			"record_type": "pull_request",
			"user": "vosslab",
			"repo_full_name": "vosslab/alpha_repo",
			"repo_name": "alpha_repo",
			"event_time": "2026-02-21T15:00:00+00:00",
			"title": "weekly patch",
		},
		{
			"record_type": "run_summary",
			"user": "vosslab",
			"window_start": "2026-02-15T00:00:00+00:00",
			"window_end": "2026-02-22T00:00:00+00:00",
		},
	]
	write_jsonl(str(jsonl_path), records)
	outline = github_data_to_outline.parse_jsonl_to_outline(str(jsonl_path))

	assert outline["user"] == "vosslab"
	assert outline["totals"]["repos"] == 1
	assert outline["totals"]["repo_records"] == 1
	assert outline["totals"]["commit_records"] == 1
	assert outline["totals"]["issue_records"] == 1
	assert outline["totals"]["pull_request_records"] == 1
	assert outline["repo_activity"][0]["repo_full_name"] == "vosslab/alpha_repo"
	assert outline["repo_activity"][0]["total_activity"] == 3
	assert outline["notable_commit_messages"][0] == "add parser stage"


#============================================
def test_render_outline_text_contains_sections() -> None:
	"""
	Ensure rendered text includes core headings and repo breakdown.
	"""
	outline = {
		"user": "vosslab",
		"window_start": "2026-02-15",
		"window_end": "2026-02-22",
		"totals": {
			"repos": 1,
			"repo_records": 1,
			"commit_records": 2,
			"issue_records": 0,
			"pull_request_records": 1,
		},
		"repo_activity": [
			{
				"repo_full_name": "vosslab/demo",
				"total_activity": 3,
				"commit_count": 2,
				"issue_count": 0,
				"pull_request_count": 1,
				"description": "demo repository",
				"language": "Python",
				"commit_messages": ["first update"],
				"issue_titles": [],
				"pull_request_titles": ["add feature"],
			},
		],
		"notable_commit_messages": ["first update"],
	}
	text = github_data_to_outline.render_outline_text(outline)
	assert "GitHub Weekly Outline" in text
	assert "Repository Breakdown" in text
	assert "vosslab/demo" in text


#============================================
def test_write_repo_outline_shards(tmp_path) -> None:
	"""
	Ensure repo-shard JSON/TXT files and manifest are written.
	"""
	outline = {
		"generated_at": "2026-02-22T00:00:00+00:00",
		"user": "vosslab",
		"window_start": "2026-02-15",
		"window_end": "2026-02-22",
		"repo_activity": [
			{
				"repo_full_name": "vosslab/repo_one",
				"repo_name": "repo_one",
				"total_activity": 5,
				"commit_count": 3,
				"issue_count": 1,
				"pull_request_count": 1,
				"description": "first repo",
				"language": "Python",
				"commit_messages": ["add shard writer"],
				"issue_titles": ["track shard split"],
				"pull_request_titles": ["ship shard output"],
			},
			{
				"repo_full_name": "vosslab/repo_two",
				"repo_name": "repo_two",
				"total_activity": 2,
				"commit_count": 2,
				"issue_count": 0,
				"pull_request_count": 0,
				"description": "",
				"language": "",
				"commit_messages": ["cleanup parser"],
				"issue_titles": [],
				"pull_request_titles": [],
			},
		],
	}
	manifest_path = github_data_to_outline.write_repo_outline_shards(outline, str(tmp_path))
	assert os.path.isfile(manifest_path)
	with open(manifest_path, "r", encoding="utf-8") as handle:
		manifest = json.loads(handle.read())
	assert manifest["repo_count"] == 2
	first_json = manifest["repo_shards"][0]["json_path"]
	first_txt = manifest["repo_shards"][0]["txt_path"]
	assert os.path.isfile(first_json)
	assert os.path.isfile(first_txt)
	with open(first_txt, "r", encoding="utf-8") as handle:
		text = handle.read()
	assert "GitHub Repo Outline" in text
	assert "Repo: vosslab/repo_one" in text


#============================================
def test_summarize_outline_with_llm_uses_client(monkeypatch) -> None:
	"""
	LLM summary function should inject repo and global outline text.
	"""
	class FakeClient:
		def generate(self, prompt=None, messages=None, purpose=None, max_tokens=0):
			if "weekly global outline" in (purpose or ""):
				return "GLOBAL SUMMARY"
			return "REPO SUMMARY"

	def fake_create_client(transport_name: str, model_override: str):
		assert transport_name == "ollama"
		assert model_override == ""
		return FakeClient()

	monkeypatch.setattr(github_data_to_outline, "create_llm_client", fake_create_client)
	outline = {
		"user": "vosslab",
		"window_start": "2026-02-15",
		"window_end": "2026-02-22",
		"totals": {"repos": 1},
		"notable_commit_messages": [],
		"repo_activity": [
			{
				"repo_full_name": "vosslab/repo_one",
				"repo_name": "repo_one",
				"description": "",
				"language": "",
				"commit_count": 2,
				"issue_count": 1,
				"pull_request_count": 0,
				"total_activity": 3,
				"latest_event_time": "2026-02-21T12:00:00+00:00",
				"commit_messages": ["m1"],
				"issue_titles": ["i1"],
				"pull_request_titles": [],
			}
		],
	}
	result = github_data_to_outline.summarize_outline_with_llm(
		outline,
		transport_name="ollama",
		model_override="",
		max_tokens=500,
		repo_limit=0,
	)
	assert result["repo_activity"][0]["llm_repo_outline"] == "REPO SUMMARY"
	assert result["llm_global_outline"] == "GLOBAL SUMMARY"


#============================================
def test_load_cached_repo_outline_map_filters_by_window(tmp_path) -> None:
	"""
	Cache loader should only use shard outlines for the same user/window.
	"""
	good_shard = {
		"user": "vosslab",
		"window_start": "2026-02-15",
		"window_end": "2026-02-22",
		"repo_activity": {
			"repo_full_name": "vosslab/repo_one",
			"llm_repo_outline": "cached one",
		},
	}
	bad_shard = {
		"user": "vosslab",
		"window_start": "2026-02-01",
		"window_end": "2026-02-08",
		"repo_activity": {
			"repo_full_name": "vosslab/repo_two",
			"llm_repo_outline": "cached two",
		},
	}
	with open(tmp_path / "001_repo_one.json", "w", encoding="utf-8") as handle:
		json.dump(good_shard, handle)
	with open(tmp_path / "002_repo_two.json", "w", encoding="utf-8") as handle:
		json.dump(bad_shard, handle)

	outline = {
		"user": "vosslab",
		"window_start": "2026-02-15",
		"window_end": "2026-02-22",
	}
	cache_map = github_data_to_outline.load_cached_repo_outline_map(str(tmp_path), outline)
	assert cache_map == {"vosslab/repo_one": "cached one"}


#============================================
def test_summarize_outline_with_llm_reuses_cached_repo(monkeypatch, tmp_path) -> None:
	"""
	Continue mode should reuse cached repo outlines and skip repo regeneration.
	"""
	shard = {
		"user": "vosslab",
		"window_start": "2026-02-15",
		"window_end": "2026-02-22",
		"repo_activity": {
			"repo_full_name": "vosslab/repo_cached",
			"llm_repo_outline": "CACHED SUMMARY",
		},
	}
	with open(tmp_path / "001_repo_cached.json", "w", encoding="utf-8") as handle:
		json.dump(shard, handle)

	generated_purposes = []

	class FakeClient:
		def generate(self, prompt=None, messages=None, purpose=None, max_tokens=0):
			generated_purposes.append(purpose or "")
			if "weekly global outline" in (purpose or ""):
				return "GLOBAL SUMMARY"
			return "NEW REPO SUMMARY"

	def fake_create_client(transport_name: str, model_override: str):
		assert transport_name == "ollama"
		assert model_override == ""
		return FakeClient()

	monkeypatch.setattr(github_data_to_outline, "create_llm_client", fake_create_client)
	outline = {
		"user": "vosslab",
		"window_start": "2026-02-15",
		"window_end": "2026-02-22",
		"totals": {"repos": 2},
		"notable_commit_messages": [],
		"repo_activity": [
			{
				"repo_full_name": "vosslab/repo_cached",
				"repo_name": "repo_cached",
				"description": "",
				"language": "",
				"commit_count": 2,
				"issue_count": 1,
				"pull_request_count": 0,
				"total_activity": 3,
				"latest_event_time": "2026-02-21T12:00:00+00:00",
				"commit_messages": ["m1"],
				"issue_titles": ["i1"],
				"pull_request_titles": [],
			},
			{
				"repo_full_name": "vosslab/repo_new",
				"repo_name": "repo_new",
				"description": "",
				"language": "",
				"commit_count": 1,
				"issue_count": 0,
				"pull_request_count": 0,
				"total_activity": 1,
				"latest_event_time": "2026-02-21T11:00:00+00:00",
				"commit_messages": ["m2"],
				"issue_titles": [],
				"pull_request_titles": [],
			},
		],
	}
	result = github_data_to_outline.summarize_outline_with_llm(
		outline,
		transport_name="ollama",
		model_override="",
		max_tokens=500,
		repo_limit=0,
		repo_shards_dir=str(tmp_path),
		continue_mode=True,
	)
	assert result["repo_activity"][0]["llm_repo_outline"] == "CACHED SUMMARY"
	assert result["repo_activity"][1]["llm_repo_outline"] == "NEW REPO SUMMARY"
	assert result["llm_cached_repo_outline_count"] == 1
	assert result["llm_generated_repo_outline_count"] == 1
	assert generated_purposes == ["weekly repo outline", "weekly global outline"]
