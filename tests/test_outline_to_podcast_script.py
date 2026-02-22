import os
import sys

import git_file_utils


REPO_ROOT = git_file_utils.get_repo_root()
PIPELINE_DIR = os.path.join(REPO_ROOT, "pipeline")
if PIPELINE_DIR not in sys.path:
	sys.path.insert(0, PIPELINE_DIR)

import outline_to_podcast_script


#============================================
def sample_outline() -> dict:
	"""
	Create compact outline payload for podcast generation tests.
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
		"notable_commit_messages": ["c1", "c2"],
	}


#============================================
def test_compute_repo_pass_word_target_formula() -> None:
	"""
	Per-repo target should follow max(100, ceil((2*L)/(N-1))).
	"""
	assert outline_to_podcast_script.compute_repo_pass_word_target(6, 500) == 200
	assert outline_to_podcast_script.compute_repo_pass_word_target(3, 500) == 500
	assert outline_to_podcast_script.compute_repo_pass_word_target(2, 500) == 1000
	assert outline_to_podcast_script.compute_repo_pass_word_target(20, 500) == 100
	assert outline_to_podcast_script.compute_repo_pass_word_target(1, 500) == 500


#============================================
def test_parse_generated_script_lines_salvages_plain_text() -> None:
	"""
	Parser should salvage unlabeled text into speaker-assigned lines.
	"""
	speakers = outline_to_podcast_script.build_speaker_labels(3)
	lines = outline_to_podcast_script.parse_generated_script_lines(
		"Plain sentence one. Plain sentence two.",
		speakers,
	)
	used = {speaker for speaker, _ in lines}
	assert used.issubset(set(speakers))
	assert len(lines) >= 1


#============================================
def test_generate_podcast_lines_with_llm_repo_then_final(monkeypatch, tmp_path) -> None:
	"""
	Generation should run repo-pass then final trim pass and keep speakers.
	"""
	responses = [
		(
			"SPEAKER_1: alpha_repo had 8 commits today.\n"
			"SPEAKER_2: It also moved 3 pull requests and 2 issues.\n"
			"SPEAKER_3: The repo stayed focused on Python automation."
		),
		(
			"SPEAKER_1: alpha_repo delivered 8 commits.\n"
			"SPEAKER_2: The team handled 3 pull requests and 2 issues.\n"
			"SPEAKER_3: Momentum stayed steady across the daily cycle."
		),
	]

	class FakeClient:
		def generate(self, prompt=None, messages=None, purpose=None, max_tokens=0):
			return responses.pop(0)

	def fake_create_client(transport_name: str, model_override: str, quiet: bool):
		assert transport_name == "ollama"
		assert model_override == ""
		assert quiet is False
		return FakeClient()

	monkeypatch.setattr(outline_to_podcast_script, "create_llm_client", fake_create_client)
	speakers = outline_to_podcast_script.build_speaker_labels(3)
	lines = outline_to_podcast_script.generate_podcast_lines_with_llm(
		sample_outline(),
		speaker_labels=speakers,
		transport_name="ollama",
		model_override="",
		max_tokens=1200,
		word_limit=80,
		continue_mode=False,
		repo_draft_cache_dir=str(tmp_path),
	)
	used = {speaker for speaker, _ in lines}
	assert used == set(speakers)
	assert outline_to_podcast_script.count_script_words(lines) <= 80
