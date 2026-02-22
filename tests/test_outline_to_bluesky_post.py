import os
import sys

import git_file_utils


REPO_ROOT = git_file_utils.get_repo_root()
PIPELINE_DIR = os.path.join(REPO_ROOT, "pipeline")
if PIPELINE_DIR not in sys.path:
	sys.path.insert(0, PIPELINE_DIR)

import outline_to_bluesky_post


#============================================
def sample_outline() -> dict:
	"""
	Create compact outline payload for Bluesky generation tests.
	"""
	return {
		"user": "vosslab",
		"window_start": "2026-02-21",
		"window_end": "2026-02-22",
		"totals": {
			"repos": 1,
			"commit_records": 8,
			"issue_records": 2,
			"pull_request_records": 3,
		},
		"repo_activity": [
			{
				"repo_full_name": "vosslab/alpha_repo",
				"description": "alpha updates",
				"language": "Python",
				"commit_count": 8,
				"issue_count": 2,
				"pull_request_count": 3,
				"latest_event_time": "2026-02-21T12:00:00+00:00",
				"commit_messages": ["c1", "c2"],
				"issue_titles": ["i1"],
				"pull_request_titles": ["p1"],
			},
		],
	}


#============================================
def test_compute_repo_pass_char_target_formula() -> None:
	"""
	Per-repo target should follow max(100, ceil((2*L)/(N-1))).
	"""
	assert outline_to_bluesky_post.compute_repo_pass_char_target(6, 140) == 100
	assert outline_to_bluesky_post.compute_repo_pass_char_target(3, 140) == 140
	assert outline_to_bluesky_post.compute_repo_pass_char_target(2, 140) == 280
	assert outline_to_bluesky_post.compute_repo_pass_char_target(20, 140) == 100
	assert outline_to_bluesky_post.compute_repo_pass_char_target(1, 140) == 140


#============================================
def test_normalize_bluesky_text_collapses_whitespace() -> None:
	"""
	Normalization should flatten whitespace and trim.
	"""
	text = outline_to_bluesky_post.normalize_bluesky_text("  one\n\n two   three  ")
	assert text == "one two three"


#============================================
def test_generate_bluesky_text_with_llm_repo_then_final(monkeypatch, tmp_path) -> None:
	"""
	Generation should run repo-pass then final trim pass.
	"""
	responses = [
		"vosslab/alpha_repo shipped 8 commits and 3 PRs.",
		"vosslab/alpha_repo moved fast: 8 commits, 3 PRs, 2 issues.",
	]

	class FakeClient:
		def generate(self, prompt=None, messages=None, purpose=None, max_tokens=0):
			return responses.pop(0)

	def fake_create_client(transport_name: str, model_override: str, quiet: bool):
		assert transport_name == "ollama"
		assert model_override == ""
		assert quiet is False
		return FakeClient()

	monkeypatch.setattr(outline_to_bluesky_post, "create_llm_client", fake_create_client)
	text = outline_to_bluesky_post.generate_bluesky_text_with_llm(
		sample_outline(),
		transport_name="ollama",
		model_override="",
		max_tokens=1200,
		char_limit=140,
		continue_mode=False,
		repo_draft_cache_dir=str(tmp_path),
	)
	assert "vosslab/alpha_repo" in text
	assert len(text) > 10
