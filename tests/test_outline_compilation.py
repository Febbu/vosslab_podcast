import os
import sys

import git_file_utils


REPO_ROOT = git_file_utils.get_repo_root()
PIPELINE_DIR = os.path.join(REPO_ROOT, "pipeline")
if PIPELINE_DIR not in sys.path:
	sys.path.insert(0, PIPELINE_DIR)

import outline_compilation


#============================================
def test_merge_repo_activity_preserves_llm_repo_outline() -> None:
	"""
	Longest llm_repo_outline should survive merge across multiple days.
	"""
	merged = {}
	# day 1: short outline
	bucket_day1 = {
		"repo_full_name": "vosslab/test_repo",
		"repo_name": "test_repo",
		"commit_count": 3,
		"llm_repo_outline": "short outline",
	}
	outline_compilation.merge_repo_activity(merged, bucket_day1)
	assert merged["vosslab/test_repo"]["llm_repo_outline"] == "short outline"
	# day 2: longer outline replaces short one
	bucket_day2 = {
		"repo_full_name": "vosslab/test_repo",
		"repo_name": "test_repo",
		"commit_count": 5,
		"llm_repo_outline": "this is a much longer outline with more detail and content",
	}
	outline_compilation.merge_repo_activity(merged, bucket_day2)
	assert "much longer outline" in merged["vosslab/test_repo"]["llm_repo_outline"]
	# day 3: shorter outline does not replace
	bucket_day3 = {
		"repo_full_name": "vosslab/test_repo",
		"repo_name": "test_repo",
		"commit_count": 1,
		"llm_repo_outline": "tiny",
	}
	outline_compilation.merge_repo_activity(merged, bucket_day3)
	assert "much longer outline" in merged["vosslab/test_repo"]["llm_repo_outline"]


#============================================
def test_compile_outlines_preserves_llm_global_outline() -> None:
	"""
	Compiled output should contain the longest global outline.
	"""
	outlines = [
		{
			"user": "vosslab",
			"window_start": "2026-02-20",
			"window_end": "2026-02-20",
			"totals": {"repos": 1, "commit_records": 2},
			"repo_activity": [
				{
					"repo_full_name": "vosslab/alpha",
					"commit_count": 2,
				},
			],
			"llm_global_outline": "short global",
		},
		{
			"user": "vosslab",
			"window_start": "2026-02-21",
			"window_end": "2026-02-21",
			"totals": {"repos": 1, "commit_records": 3},
			"repo_activity": [
				{
					"repo_full_name": "vosslab/alpha",
					"commit_count": 3,
				},
			],
			"llm_global_outline": "this is a much longer global outline with more context",
		},
	]
	compiled = outline_compilation.compile_outlines(outlines)
	assert "much longer global outline" in compiled["llm_global_outline"]
