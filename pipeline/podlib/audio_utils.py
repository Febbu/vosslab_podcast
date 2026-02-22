"""
Shared audio utilities for podcast pipeline TTS scripts.
"""

# Standard Library
import re
import shutil
import subprocess


SAY_LOCALE_TOKEN_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.@-]*$")


#============================================
def parse_script_lines(script_text: str) -> list[tuple[str, str]]:
	"""
	Parse ROLE: text lines from script input.

	Returns list of (speaker_label, text) tuples.
	"""
	lines: list[tuple[str, str]] = []
	for raw in script_text.splitlines():
		line = raw.strip()
		if not line:
			continue
		if ":" not in line:
			continue
		speaker, text = line.split(":", 1)
		speaker = speaker.strip().upper()
		text = text.strip()
		if not speaker or not text:
			continue
		lines.append((speaker, text))
	return lines


#============================================
def get_unique_speakers(lines: list[tuple[str, str]]) -> list[str]:
	"""
	Return speaker labels in first-seen order.
	"""
	labels: list[str] = []
	for speaker, _text in lines:
		if speaker not in labels:
			labels.append(speaker)
	return labels


#============================================
def build_single_voice_narration(script_text: str, lines: list[tuple[str, str]]) -> str:
	"""
	Build one narration block from speaker lines or raw text.

	Strips speaker labels and joins all text into a single block.
	Falls back to raw script text if no parsed lines are available.
	"""
	if lines:
		parts = [text.strip() for _speaker, text in lines if text.strip()]
		return " ".join(parts).strip()
	return " ".join(script_text.split()).strip()


#============================================
def parse_say_voices(raw_output: str) -> list[str]:
	"""
	Parse `say -v ?` output into ordered voice names.
	"""
	voices: list[str] = []
	for line in raw_output.splitlines():
		text = line.rstrip()
		if "#" not in text:
			continue
		left = text.split("#", 1)[0].strip()
		if not left:
			continue
		parts = left.split()
		if len(parts) < 2:
			continue
		locale_candidate = parts[-1]
		if ("_" not in locale_candidate) or (not SAY_LOCALE_TOKEN_RE.match(locale_candidate)):
			continue
		voice_name = " ".join(parts[:-1]).strip()
		if voice_name and (voice_name not in voices):
			voices.append(voice_name)
	return voices


#============================================
def list_available_say_voices() -> list[str]:
	"""
	Query installed say voices from the local system.
	"""
	if shutil.which("say") is None:
		raise RuntimeError("macOS `say` command is required but not found.")
	result = subprocess.run(
		["say", "-v", "?"],
		check=True,
		capture_output=True,
		text=True,
	)
	return parse_say_voices(result.stdout)


#============================================
def resolve_voice_name(requested_voice: str, voices: list[str]) -> str:
	"""
	Resolve configured voice against installed voices.
	"""
	requested = requested_voice.strip()
	if not requested:
		return ""
	# exact match (case-insensitive)
	for voice in voices:
		if voice.lower() == requested.lower():
			return voice
	# special Siri handling
	if requested.lower() == "siri":
		for voice in voices:
			if "siri" in voice.lower():
				return voice
		return ""
	# partial match
	partial = [voice for voice in voices if requested.lower() in voice.lower()]
	if len(partial) == 1:
		return partial[0]
	if len(partial) > 1:
		raise RuntimeError(
			"Voice name is ambiguous: "
			+ requested
			+ ". Matches: "
			+ ", ".join(partial[:8])
		)
	raise RuntimeError(
		"Voice not found: "
		+ requested
		+ ". Use --list-voices to inspect installed names."
	)


#============================================
def convert_to_mp3(input_path: str, mp3_path: str) -> None:
	"""
	Convert audio file (AIFF or WAV) to MP3 using lame.
	"""
	if shutil.which("lame") is None:
		raise RuntimeError("lame is required for MP3 conversion but not found.")
	# -V 2 is variable bitrate quality 2 (~190 kbps), good speech quality
	command = ["lame", "-V", "2", "--quiet", input_path, mp3_path]
	subprocess.run(command, check=True)
