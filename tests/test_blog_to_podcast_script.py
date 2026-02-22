import os
import sys

import git_file_utils


REPO_ROOT = git_file_utils.get_repo_root()
PIPELINE_DIR = os.path.join(REPO_ROOT, "pipeline")
if PIPELINE_DIR not in sys.path:
	sys.path.insert(0, PIPELINE_DIR)

import blog_to_podcast_script


SAMPLE_BLOG = (
	"# vosslab daily update\n\n"
	"Today vosslab/alpha_repo received 8 commits and 3 pull requests.\n"
	"The main focus was Python automation tooling.\n"
)


#============================================
def test_build_speaker_labels_returns_q101_names() -> None:
	"""
	Speaker labels should use Q101 personality names.
	"""
	assert blog_to_podcast_script.build_speaker_labels(1) == ["BHOST"]
	assert blog_to_podcast_script.build_speaker_labels(2) == ["BHOST", "KCOLOR"]
	assert blog_to_podcast_script.build_speaker_labels(3) == ["BHOST", "KCOLOR", "CPRODUCER"]


#============================================
def test_parse_generated_script_lines_salvages_plain_text() -> None:
	"""
	Parser should salvage unlabeled text into speaker-assigned lines.
	"""
	speakers = blog_to_podcast_script.build_speaker_labels(3)
	lines = blog_to_podcast_script.parse_generated_script_lines(
		"Plain sentence one. Plain sentence two.",
		speakers,
	)
	used = {speaker for speaker, _ in lines}
	assert used.issubset(set(speakers))
	assert len(lines) >= 1


#============================================
def test_count_script_words() -> None:
	"""
	Word count should total all speaker line words.
	"""
	lines = [("BHOST", "one two three"), ("KCOLOR", "four five")]
	assert blog_to_podcast_script.count_script_words(lines) == 5


#============================================
def test_build_podcast_lines_from_blog() -> None:
	"""
	Deterministic fallback should produce lines from blog markdown.
	"""
	speakers = blog_to_podcast_script.build_speaker_labels(3)
	lines = blog_to_podcast_script.build_podcast_lines(SAMPLE_BLOG, speakers)
	used = {speaker for speaker, _ in lines}
	assert used.issubset(set(speakers))
	assert len(lines) >= 1


#============================================
def test_generate_podcast_lines_with_llm_single_pass(monkeypatch) -> None:
	"""
	Generation should produce speaker lines from blog via single LLM call.
	"""
	class FakeClient:
		def generate(self, prompt=None, messages=None, purpose=None, max_tokens=0):
			return (
				"BHOST: alpha_repo had 8 commits today.\n"
				"KCOLOR: It also moved 3 pull requests and 2 issues.\n"
				"CPRODUCER: The repo stayed focused on Python automation."
			)

	def fake_create_client(transport_name: str, model_override: str, quiet: bool):
		return FakeClient()

	monkeypatch.setattr(blog_to_podcast_script, "create_llm_client", fake_create_client)
	speakers = blog_to_podcast_script.build_speaker_labels(3)
	lines = blog_to_podcast_script.generate_podcast_lines_with_llm(
		SAMPLE_BLOG,
		speaker_labels=speakers,
		transport_name="ollama",
		model_override="",
		max_tokens=1200,
		word_limit=80,
	)
	used = {speaker for speaker, _ in lines}
	assert used == set(speakers)
	assert blog_to_podcast_script.count_script_words(lines) <= 80
