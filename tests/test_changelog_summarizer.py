import os
import sys

import git_file_utils


REPO_ROOT = git_file_utils.get_repo_root()
PIPELINE_DIR = os.path.join(REPO_ROOT, "pipeline")
if PIPELINE_DIR not in sys.path:
	sys.path.insert(0, PIPELINE_DIR)

import changelog_summarizer


#============================================
def test_chunk_text_basic() -> None:
	"""
	Text longer than chunk_size should split into multiple overlapping chunks.
	"""
	# 9000 chars with chunk_size=3000 and overlap=500 -> step=2500
	# chunks at: [0:3000], [2500:5500], [5000:8000], [7500:9000]
	text = "a" * 9000
	chunks = changelog_summarizer.chunk_text(text, chunk_size=3000, overlap=500)
	assert len(chunks) >= 3
	# each chunk except possibly the last should be 3000 chars
	for chunk in chunks[:-1]:
		assert len(chunk) == 3000


#============================================
def test_chunk_text_short() -> None:
	"""
	Text shorter than chunk_size should return a single chunk.
	"""
	text = "short changelog entry"
	chunks = changelog_summarizer.chunk_text(text, chunk_size=3000, overlap=500)
	assert len(chunks) == 1
	assert chunks[0] == text


#============================================
def test_chunk_text_empty() -> None:
	"""
	Empty text should return an empty list.
	"""
	chunks = changelog_summarizer.chunk_text("", chunk_size=3000, overlap=500)
	assert chunks == []


#============================================
def test_chunk_text_overlap() -> None:
	"""
	Adjacent chunks should share overlapping content.
	"""
	# build text with identifiable content at overlap boundary
	text = "A" * 2800 + "OVERLAP" + "B" * 2800
	chunks = changelog_summarizer.chunk_text(text, chunk_size=3000, overlap=500)
	assert len(chunks) >= 2
	# the overlap marker should appear in both first and second chunk
	# first chunk: [0:3000] includes "OVERLAP" at position 2800
	assert "OVERLAP" in chunks[0]
	# second chunk starts at 2500, so it includes position 2800 too
	assert "OVERLAP" in chunks[1]


#============================================
def test_summarize_long_changelog_passthrough() -> None:
	"""
	Text under threshold should be returned unchanged without LLM calls.
	"""
	short_text = "Small changelog update."
	result = changelog_summarizer.summarize_long_changelog(
		client=None,
		entry_text=short_text,
		threshold=6000,
	)
	assert result == short_text


#============================================
def test_summarize_long_changelog_calls_llm() -> None:
	"""
	Text over threshold should be chunked and each chunk summarized via LLM.
	"""
	call_count = [0]

	class FakeClient:
		def generate(self, prompt=None, purpose=None, max_tokens=0):
			call_count[0] += 1
			return f"Summary of chunk {call_count[0]}."

	# 7000 chars with chunk_size=3000, overlap=500 -> multiple chunks
	long_text = "x" * 7000
	result = changelog_summarizer.summarize_long_changelog(
		client=FakeClient(),
		entry_text=long_text,
		threshold=6000,
		chunk_size=3000,
		overlap=500,
	)
	# should have called the LLM for each chunk
	assert call_count[0] >= 2
	# result should contain the summary text from each call
	assert "Summary of chunk 1" in result
	assert "Summary of chunk 2" in result


#============================================
def test_summarize_bucket_changelogs_mutates_entries() -> None:
	"""
	summarize_bucket_changelogs should replace long entry_text in place.
	"""
	call_count = [0]

	class FakeClient:
		def generate(self, prompt=None, purpose=None, max_tokens=0):
			call_count[0] += 1
			return "Condensed summary."

	bucket = {
		"changelog_entries": [
			{"heading": "## 2026-02-22", "entry_text": "y" * 7000, "date": "2026-02-22"},
			{"heading": "## 2026-02-21", "entry_text": "short entry", "date": "2026-02-21"},
		],
	}
	changelog_summarizer.summarize_bucket_changelogs(
		client=FakeClient(),
		bucket=bucket,
		threshold=6000,
	)
	# first entry should be replaced with concatenated chunk summaries
	assert "Condensed summary." in bucket["changelog_entries"][0]["entry_text"]
	# original text should be gone
	assert "y" * 100 not in bucket["changelog_entries"][0]["entry_text"]
	# second entry should be unchanged (under threshold)
	assert bucket["changelog_entries"][1]["entry_text"] == "short entry"
