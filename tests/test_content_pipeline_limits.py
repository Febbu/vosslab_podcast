import os
import sys

import git_file_utils


REPO_ROOT = git_file_utils.get_repo_root()
PIPELINE_DIR = os.path.join(REPO_ROOT, "pipeline")
if PIPELINE_DIR not in sys.path:
	sys.path.insert(0, PIPELINE_DIR)

import outline_to_blog_post
import blog_to_bluesky_post
import blog_to_podcast_script
from podlib import pipeline_text_utils


SAMPLE_BLOG = (
	"# Weekly Update\n\n"
	"## Highlights\n\n"
	"This week included several repository updates with commits, pull requests, "
	"and issue triage across services and tooling components for content delivery.\n\n"
	"## Repo Notes\n\n"
	"- alpha repo migration complete\n"
	"- beta analytics refactor underway\n"
)


#============================================
def test_blog_trim_respects_word_limit() -> None:
	"""
	Ensure Markdown blog text can be trimmed to a hard word limit.
	"""
	trimmed = outline_to_blog_post.trim_markdown_to_word_limit(SAMPLE_BLOG, 25)
	word_count = pipeline_text_utils.count_words(trimmed)
	assert word_count <= 25


#============================================
def test_bluesky_trim_respects_char_limit() -> None:
	"""
	Ensure Bluesky text can be clamped to 140 characters.
	"""
	text = blog_to_bluesky_post.build_bluesky_text_from_blog(SAMPLE_BLOG)
	trimmed = pipeline_text_utils.trim_to_char_limit(text, 140)
	assert len(trimmed) <= 140


#============================================
def test_podcast_generation_respects_limits_and_speakers() -> None:
	"""
	Ensure generated podcast script lines use N speakers and word limits.
	"""
	labels = blog_to_podcast_script.build_speaker_labels(3)
	lines = blog_to_podcast_script.build_podcast_lines(SAMPLE_BLOG, labels)
	trimmed = blog_to_podcast_script.trim_lines_to_word_limit(lines, 160)
	word_count = blog_to_podcast_script.count_script_words(trimmed)
	used_speakers = {speaker for speaker, _text in trimmed}
	assert word_count <= 160
	assert used_speakers == set(labels)
