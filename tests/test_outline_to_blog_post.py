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
	Prompt should require Markdown output and anti-CTA constraints.
	"""
	prompt = outline_to_blog_post.build_blog_markdown_prompt(sample_outline(), 500)
	assert "Markdown only" in prompt
	assert "about 500 words" in prompt
	assert "vosslab/alpha_repo" in prompt
	assert "Do not ask readers to comment" in prompt
	assert "daily engineering blog update" in prompt


#============================================
def test_compute_repo_pass_word_target_formula() -> None:
	"""
	Per-repo target should follow max(100, ceil((2*L)/(N-1))).
	"""
	assert outline_to_blog_post.compute_repo_pass_word_target(6, 500) == 200
	assert outline_to_blog_post.compute_repo_pass_word_target(3, 500) == 500
	assert outline_to_blog_post.compute_repo_pass_word_target(2, 500) == 1000
	assert outline_to_blog_post.compute_repo_pass_word_target(20, 500) == 100
	assert outline_to_blog_post.compute_repo_pass_word_target(1, 500) == 500


#============================================
def test_generate_blog_markdown_with_llm_retries_for_limit(monkeypatch) -> None:
	"""
	Generation should run repo-pass then final trim pass.
	"""
	responses = [
		"# Title\n\n" + ("word " * 80).strip(),
		"# Title\n\n## Summary\n\n" + ("short final summary text " * 13).strip(),
	]

	class FakeClient:
		def generate(self, prompt=None, messages=None, purpose=None, max_tokens=0):
			return responses.pop(0)

	def fake_create_client(transport_name: str, model_override: str, quiet: bool):
		assert transport_name == "ollama"
		assert model_override == ""
		assert quiet is False
		return FakeClient()

	monkeypatch.setattr(outline_to_blog_post, "create_llm_client", fake_create_client)
	markdown = outline_to_blog_post.generate_blog_markdown_with_llm(
		sample_outline(),
		transport_name="ollama",
		model_override="",
		max_tokens=1200,
		word_limit=50,
	)
	assert pipeline_text_utils.count_words(markdown) >= 50
	assert markdown.startswith("# Title")


#============================================
def test_blog_quality_issue_flags_error_payload() -> None:
	"""
	Quality check should flag model error payload text.
	"""
	issue = outline_to_blog_post.blog_quality_issue(
		'{"error_code":-6,"error":"GenerationError"}',
	)
	assert "error" in issue


#============================================
def test_blog_quality_issue_allows_short_markdown() -> None:
	"""
	Word count should be a target, not a hard validity requirement.
	"""
	issue = outline_to_blog_post.blog_quality_issue("# Title\n\nTiny update.")
	assert issue == ""


#============================================
def test_normalize_markdown_blog_promotes_h2_to_h1() -> None:
	"""
	Salvage should promote leading H2 to H1.
	"""
	text = outline_to_blog_post.normalize_markdown_blog("## Update\n\nBody")
	assert text.startswith("# Update")


#============================================
def test_normalize_markdown_blog_injects_default_h1() -> None:
	"""
	Salvage should inject a default H1 when none exists.
	"""
	text = outline_to_blog_post.normalize_markdown_blog("Plain opening line.\n\nMore text.")
	assert text.startswith("# Daily Engineering Update")


#============================================
def test_date_stamp_output_path_adds_local_date() -> None:
	"""
	Output filename should gain a local-date suffix when missing.
	"""
	path = outline_to_blog_post.date_stamp_output_path("out/blog_post.md", "2026-02-22")
	assert path.endswith("out/blog_post_2026-02-22.md")


#============================================
def test_date_stamp_output_path_keeps_existing_date() -> None:
	"""
	Output filename should not duplicate an existing date stamp.
	"""
	path = outline_to_blog_post.date_stamp_output_path(
		"out/blog_post_2026-02-22.md",
		"2026-02-22",
	)
	assert path.endswith("out/blog_post_2026-02-22.md")
