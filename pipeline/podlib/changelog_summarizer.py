"""Changelog chunk summarizer for long changelog entries.

Breaks long changelog text into overlapping chunks, summarizes each chunk
via an LLM, and concatenates the summaries into a shorter but complete
representation of the full changelog content.
"""

from podlib import prompt_loader


#============================================
def chunk_text(text: str, chunk_size: int = 2250, overlap: int = 250) -> list[str]:
	"""
	Split text into overlapping chunks.

	Each chunk is chunk_size chars long. The next chunk starts at
	chunk_size - overlap from the previous start. The last chunk
	gets whatever remains (no minimum size).

	Args:
		text: the full text to split.
		chunk_size: maximum characters per chunk.
		overlap: overlap between consecutive chunks.

	Returns:
		List of chunk strings.
	"""
	if not text:
		return []
	if len(text) <= chunk_size:
		return [text]
	chunks = []
	# step forward by chunk_size minus overlap each iteration
	step = chunk_size - overlap
	start = 0
	while start < len(text):
		end = start + chunk_size
		chunks.append(text[start:end])
		start += step
		# avoid a tiny trailing chunk that duplicates the previous chunk's tail
		if start < len(text) and (len(text) - start) <= overlap:
			chunks.append(text[start:])
			break
	return chunks


#============================================
def summarize_changelog_chunks(
	client,
	chunks: list[str],
	max_tokens: int = 1024,
) -> str:
	"""
	Summarize each changelog chunk with the LLM and concatenate results.

	Args:
		client: local-llm-wrapper LLMClient instance.
		chunks: list of text chunks to summarize.
		max_tokens: max generation tokens per LLM call.

	Returns:
		Combined summary string with double-newline separators.
	"""
	template = prompt_loader.load_prompt("changelog_chunk_summary.txt")
	summaries = []
	for i, chunk in enumerate(chunks):
		prompt = prompt_loader.render_prompt(template, {"chunk_text": chunk})
		# generate summary for this chunk
		summary = client.generate(
			prompt=prompt,
			purpose=f"changelog chunk summary {i + 1}/{len(chunks)}",
			max_tokens=max_tokens,
		).strip()
		if summary:
			summaries.append(summary)
	combined = "\n\n".join(summaries)
	return combined


#============================================
def summarize_long_changelog(
	client,
	entry_text: str,
	threshold: int = 6000,
	chunk_size: int = 2250,
	overlap: int = 250,
	max_tokens: int = 1024,
	log_fn=None,
) -> str:
	"""
	Summarize a changelog entry if it exceeds the character threshold.

	If the entry text is at or below the threshold, it is returned unchanged.
	Otherwise the text is split into overlapping chunks and each chunk is
	summarized via the LLM.

	Args:
		client: local-llm-wrapper LLMClient instance.
		entry_text: raw changelog entry text.
		threshold: character count above which summarization triggers.
		chunk_size: characters per chunk for splitting.
		overlap: overlap between consecutive chunks.
		max_tokens: max generation tokens per LLM call.
		log_fn: optional callable for progress logging.

	Returns:
		Original text (if short enough) or concatenated chunk summaries.
	"""
	if len(entry_text) <= threshold:
		return entry_text
	chunks = chunk_text(entry_text, chunk_size=chunk_size, overlap=overlap)
	if log_fn:
		log_fn(f"Summarizing changelog entry ({len(entry_text)} chars) in {len(chunks)} chunks")
	summary = summarize_changelog_chunks(client, chunks, max_tokens=max_tokens)
	return summary


#============================================
def summarize_bucket_changelogs(
	client,
	bucket: dict,
	threshold: int = 6000,
	log_fn=None,
) -> None:
	"""
	Summarize long changelog entries in a repo activity bucket in place.

	Iterates over bucket['changelog_entries'] and replaces each entry_text
	that exceeds the threshold with a shorter LLM summary.

	Args:
		client: local-llm-wrapper LLMClient instance.
		bucket: repo activity bucket dict with changelog_entries.
		threshold: character count above which summarization triggers.
		log_fn: optional callable for progress logging.
	"""
	entries = bucket.get("changelog_entries", [])
	for entry in entries:
		text = entry.get("entry_text", "")
		if len(text) > threshold:
			entry["entry_text"] = summarize_long_changelog(
				client, text, threshold=threshold, log_fn=log_fn,
			)
