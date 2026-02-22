import os
import sys

import git_file_utils


REPO_ROOT = git_file_utils.get_repo_root()
PIPELINE_DIR = os.path.join(REPO_ROOT, "pipeline")
if PIPELINE_DIR not in sys.path:
	sys.path.insert(0, PIPELINE_DIR)

import blog_to_bluesky_post


SAMPLE_BLOG = (
	"# vosslab daily update\n\n"
	"Today vosslab/alpha_repo received 8 commits and 3 pull requests.\n"
	"The main focus was Python automation tooling.\n"
)


#============================================
def test_normalize_bluesky_text_collapses_whitespace() -> None:
	"""
	Normalization should flatten whitespace and trim.
	"""
	text = blog_to_bluesky_post.normalize_bluesky_text("  one\n\n two   three  ")
	assert text == "one two three"


#============================================
def test_strip_all_xml_tags_removes_tags() -> None:
	"""
	XML tag stripper should remove all XML-like tags.
	"""
	text = blog_to_bluesky_post.strip_all_xml_tags("<repo>hello</repo> world")
	assert text == "hello world"


#============================================
def test_bluesky_quality_issue_empty() -> None:
	"""
	Empty text should be flagged as an issue.
	"""
	assert blog_to_bluesky_post.bluesky_quality_issue("") != ""
	assert blog_to_bluesky_post.bluesky_quality_issue("good text") == ""


#============================================
def test_build_bluesky_text_from_blog_extracts_title() -> None:
	"""
	Deterministic fallback should extract H1 title and first sentence.
	"""
	result = blog_to_bluesky_post.build_bluesky_text_from_blog(SAMPLE_BLOG)
	assert "vosslab daily update" in result
	assert len(result) > 10


#============================================
def test_generate_bluesky_text_with_llm_single_pass(monkeypatch) -> None:
	"""
	Generation should produce text from blog markdown via single LLM call.
	"""
	class FakeClient:
		def generate(self, prompt=None, messages=None, purpose=None, max_tokens=0):
			return "alpha_repo shipped 8 commits and 3 PRs today."

	def fake_create_client(transport_name: str, model_override: str, quiet: bool):
		return FakeClient()

	monkeypatch.setattr(blog_to_bluesky_post, "create_llm_client", fake_create_client)
	text = blog_to_bluesky_post.generate_bluesky_text_with_llm(
		SAMPLE_BLOG,
		transport_name="ollama",
		model_override="",
		max_tokens=1200,
		char_limit=280,
	)
	assert "alpha_repo" in text
	assert len(text) > 10
