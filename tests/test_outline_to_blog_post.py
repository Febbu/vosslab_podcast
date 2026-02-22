import os
import sys

import git_file_utils


REPO_ROOT = git_file_utils.get_repo_root()
PIPELINE_DIR = os.path.join(REPO_ROOT, "pipeline")
if PIPELINE_DIR not in sys.path:
	sys.path.insert(0, PIPELINE_DIR)

import outline_to_blog_post
from podlib import pipeline_text_utils


#============================================
def sample_outline() -> dict:
	"""
	Create compact outline payload for blog generation tests.
	"""
	return {
		"user": "vosslab",
		"window_start": "2026-02-15",
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
		"notable_commit_messages": ["c1", "c2"],
		"llm_global_outline": "global text",
	}


#============================================
def test_build_blog_markdown_prompt_includes_markdown_constraints() -> None:
	"""
	Prompt should require Markdown output and enforce word cap.
	"""
	prompt = outline_to_blog_post.build_blog_markdown_prompt(sample_outline(), 500)
	assert "Markdown only" in prompt
	assert "about 500 words" in prompt
	assert "vosslab/alpha_repo" in prompt


#============================================
def test_generate_blog_markdown_with_llm_retries_for_limit(monkeypatch) -> None:
	"""
	Generation should retry when first response exceeds word limit.
	"""
	responses = [
		"# Title\n\n" + ("word " * 80).strip(),
		"# Title\n\n## Summary\n\nshort final summary.",
	]

	class FakeClient:
		def generate(self, prompt=None, messages=None, purpose=None, max_tokens=0):
			return responses.pop(0)

	def fake_create_client(transport_name: str, model_override: str):
		assert transport_name == "ollama"
		assert model_override == ""
		return FakeClient()

	monkeypatch.setattr(outline_to_blog_post, "create_llm_client", fake_create_client)
	markdown = outline_to_blog_post.generate_blog_markdown_with_llm(
		sample_outline(),
		transport_name="ollama",
		model_override="",
		max_tokens=1200,
		word_limit=50,
	)
	assert pipeline_text_utils.count_words(markdown) <= 50
	assert markdown.startswith("# Title")
