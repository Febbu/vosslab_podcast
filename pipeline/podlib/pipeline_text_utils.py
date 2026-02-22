import re


WORD_RE = re.compile(r"[A-Za-z0-9']+")


#============================================
def extract_words(text: str) -> list[str]:
	"""
	Return tokenized words for stable word-limit checks.
	"""
	words = WORD_RE.findall(text)
	return words


#============================================
def count_words(text: str) -> int:
	"""
	Count words using a stable regex-based tokenizer.
	"""
	words = extract_words(text)
	count = len(words)
	return count


#============================================
def trim_to_word_limit(text: str, word_limit: int) -> str:
	"""
	Trim text to a maximum word count.
	"""
	if word_limit <= 0:
		return ""
	words = extract_words(text)
	if len(words) <= word_limit:
		return text.strip()

	remaining = word_limit
	trimmed_parts = []
	for raw in text.split():
		word_count = count_words(raw)
		if word_count == 0:
			continue
		if remaining <= 0:
			break
		if word_count <= remaining:
			trimmed_parts.append(raw)
			remaining -= word_count
			continue
		break

	if not trimmed_parts:
		return ""

	trimmed_text = " ".join(trimmed_parts).strip()
	if not trimmed_text.endswith("..."):
		trimmed_text += " ..."
	return trimmed_text


#============================================
def trim_to_char_limit(text: str, char_limit: int) -> str:
	"""
	Trim text to a maximum character count.
	"""
	clean = text.strip()
	if char_limit <= 0:
		return ""
	if len(clean) <= char_limit:
		return clean
	if char_limit <= 3:
		return clean[:char_limit]
	result = clean[:char_limit - 3].rstrip() + "..."
	return result


#============================================
def assert_word_limit(text: str, word_limit: int) -> None:
	"""
	Raise when text exceeds a word limit.
	"""
	count = count_words(text)
	if count > word_limit:
		raise RuntimeError(
			f"Word limit exceeded: {count} > {word_limit}"
		)


#============================================
def assert_char_limit(text: str, char_limit: int) -> None:
	"""
	Raise when text exceeds a character limit.
	"""
	length = len(text)
	if length > char_limit:
		raise RuntimeError(
			f"Character limit exceeded: {length} > {char_limit}"
		)

