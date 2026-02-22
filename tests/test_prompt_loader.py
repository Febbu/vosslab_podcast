import os
import sys

import git_file_utils


REPO_ROOT = git_file_utils.get_repo_root()
PIPELINE_DIR = os.path.join(REPO_ROOT, "pipeline")
if PIPELINE_DIR not in sys.path:
	sys.path.insert(0, PIPELINE_DIR)

import prompt_loader


#============================================
def test_load_prompt_returns_string() -> None:
	"""
	load_prompt should return a non-empty string for an existing prompt file.
	"""
	text = prompt_loader.load_prompt("blog_markdown.txt")
	assert isinstance(text, str)
	assert len(text) > 50


#============================================
def test_load_prompt_missing_file_raises() -> None:
	"""
	load_prompt should raise FileNotFoundError for missing prompt files.
	"""
	raised = False
	try:
		prompt_loader.load_prompt("nonexistent_prompt_file.txt")
	except FileNotFoundError:
		raised = True
	assert raised


#============================================
def test_render_prompt_replaces_tokens() -> None:
	"""
	render_prompt should replace {{token}} placeholders with values.
	"""
	template = "Hello {{name}}, you have {{count}} items."
	result = prompt_loader.render_prompt(template, {
		"name": "Alice",
		"count": "42",
	})
	assert result == "Hello Alice, you have 42 items."


#============================================
def test_render_prompt_preserves_unreplaced_tokens() -> None:
	"""
	render_prompt should leave unknown tokens intact.
	"""
	template = "Value: {{known}} and {{unknown}}"
	result = prompt_loader.render_prompt(template, {"known": "yes"})
	assert result == "Value: yes and {{unknown}}"


#============================================
def test_load_and_render_round_trip() -> None:
	"""
	Load a real prompt and render it with sample values.
	"""
	template = prompt_loader.load_prompt("blog_markdown.txt")
	rendered = prompt_loader.render_prompt(template, {
		"word_limit": "500",
		"context_json": '{"user": "test"}',
	})
	# tokens should be replaced
	assert "{{word_limit}}" not in rendered
	assert "500" in rendered
	assert '{"user": "test"}' in rendered


#============================================
def test_all_prompt_files_exist() -> None:
	"""
	All expected prompt files should exist in pipeline/prompts/.
	"""
	expected_files = [
		"blog_markdown.txt",
		"blog_repo_markdown.txt",
		"blog_trim.txt",
		"blog_expand.txt",
		"bluesky_repo.txt",
		"bluesky_fallback.txt",
		"bluesky_trim.txt",
		"bluesky_summarize.txt",
		"podcast_repo.txt",
		"podcast_fallback.txt",
		"podcast_trim.txt",
		"podcast_script.txt",
		"podcast_narration.txt",
		"outline_repo.txt",
		"outline_repo_targeted.txt",
		"outline_global.txt",
		"show_intro.txt",
		"bhost.txt",
		"kcolor.txt",
		"cproducer.txt",
	]
	prompts_dir = os.path.join(REPO_ROOT, "pipeline", "prompts")
	for filename in expected_files:
		path = os.path.join(prompts_dir, filename)
		assert os.path.isfile(path), f"Missing prompt file: {filename}"
