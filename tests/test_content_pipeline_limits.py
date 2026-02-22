import os
import sys

import git_file_utils


REPO_ROOT = git_file_utils.get_repo_root()
PIPELINE_DIR = os.path.join(REPO_ROOT, "pipeline")
if PIPELINE_DIR not in sys.path:
	sys.path.insert(0, PIPELINE_DIR)

import outline_to_blog_post
import outline_to_bluesky_post
import outline_to_podcast_script
from podlib import pipeline_text_utils


#============================================
def sample_outline() -> dict:
	"""
	Build a deterministic outline payload for content-limit tests.
	"""
	return {
		"user": "vosslab",
		"window_start": "2026-02-15",
		"window_end": "2026-02-22",
		"totals": {
			"repos": 2,
			"commit_records": 14,
			"issue_records": 3,
			"pull_request_records": 4,
		},
		"repo_activity": [
			{
				"repo_full_name": "vosslab/alpha_repo",
				"repo_name": "alpha_repo",
				"description": "Alpha service and deployment updates",
				"commit_count": 10,
				"issue_count": 1,
				"pull_request_count": 3,
			},
			{
				"repo_full_name": "vosslab/beta_repo",
				"repo_name": "beta_repo",
				"description": "Beta analytics updates",
				"commit_count": 4,
				"issue_count": 2,
				"pull_request_count": 1,
			},
		],
		"notable_commit_messages": [
			"improve parsing speed for weekly ingest",
			"add speaker mapping for script audio stage",
		],
	}


#============================================
def test_blog_trim_respects_word_limit() -> None:
	"""
	Ensure Markdown blog text can be trimmed to a hard word limit.
	"""
	markdown = (
		"# Weekly Update\n\n"
		"## Highlights\n\n"
		"This week included several repository updates with commits, pull requests, "
		"and issue triage across services and tooling components for content delivery.\n\n"
		"## Repo Notes\n\n"
		"- alpha repo migration complete\n"
		"- beta analytics refactor underway\n"
	)
	trimmed = outline_to_blog_post.trim_markdown_to_word_limit(markdown, 25)
	word_count = pipeline_text_utils.count_words(trimmed)
	assert word_count <= 25


#============================================
def test_bluesky_trim_respects_char_limit() -> None:
	"""
	Ensure Bluesky text can be clamped to 140 characters.
	"""
	outline = sample_outline()
	text = outline_to_bluesky_post.build_bluesky_text(outline)
	trimmed = pipeline_text_utils.trim_to_char_limit(text, 140)
	assert len(trimmed) <= 140


#============================================
def test_podcast_generation_respects_limits_and_speakers() -> None:
	"""
	Ensure generated podcast script lines use N speakers and word limits.
	"""
	outline = sample_outline()
	labels = outline_to_podcast_script.build_speaker_labels(4)
	lines = outline_to_podcast_script.build_podcast_lines(outline, labels)
	trimmed = outline_to_podcast_script.trim_lines_to_word_limit(lines, 160)
	word_count = outline_to_podcast_script.count_script_words(trimmed)
	used_speakers = {speaker for speaker, _text in trimmed}
	assert word_count <= 160
	assert used_speakers == set(labels)
