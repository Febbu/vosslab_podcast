#!/usr/bin/env python3
import argparse
import os
import re
import shutil
import subprocess
import tempfile
from datetime import datetime

from podlib import pipeline_settings


SAY_LOCALE_TOKEN_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.@-]*$")
DEFAULT_SCRIPT_PATH = "out/podcast_script.txt"
DEFAULT_OUTPUT_PATH = "out/episode_siri.aiff"


#============================================
def log_step(message: str) -> None:
	"""
	Print one timestamped progress line.
	"""
	now_text = datetime.now().strftime("%H:%M:%S")
	print(f"[script_to_audio_say {now_text}] {message}", flush=True)


#============================================
def parse_args() -> argparse.Namespace:
	"""
	Parse command-line arguments.
	"""
	parser = argparse.ArgumentParser(
		description="Convert script text into one-voice macOS audio with say."
	)
	parser.add_argument(
		"--script",
		default=DEFAULT_SCRIPT_PATH,
		help="Path to podcast script text file.",
	)
	parser.add_argument(
		"--output",
		default=DEFAULT_OUTPUT_PATH,
		help="Path to output audio file (AIFF recommended).",
	)
	parser.add_argument(
		"--settings",
		default="settings.yaml",
		help="YAML settings path for say voice/rate defaults.",
	)
	parser.add_argument(
		"--voice",
		default=None,
		help="Optional say voice override (for example 'Siri' or 'Samantha').",
	)
	parser.add_argument(
		"--rate-wpm",
		type=int,
		default=None,
		help="Optional speaking rate words-per-minute override.",
	)
	parser.add_argument(
		"--list-voices",
		action="store_true",
		help="List available say voices and exit.",
	)
	args = parser.parse_args()
	return args


#============================================
def parse_script_lines(script_text: str) -> list[tuple[str, str]]:
	"""
	Parse ROLE: text lines from script input.
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
	for voice in voices:
		if voice.lower() == requested.lower():
			return voice
	if requested.lower() == "siri":
		for voice in voices:
			if "siri" in voice.lower():
				return voice
		return ""
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
def run_say_to_file(
	narration: str,
	output_path: str,
	voice_name: str,
	rate_wpm: int,
) -> None:
	"""
	Run macOS say command to synthesize one audio file.
	"""
	fd, tmp_path = tempfile.mkstemp(prefix="vosslab_say_", suffix=".txt")
	os.close(fd)
	try:
		with open(tmp_path, "w", encoding="utf-8") as handle:
			handle.write(narration)
			handle.write("\n")

		command = ["say"]
		if voice_name:
			command.extend(["-v", voice_name])
		command.extend(["-r", str(rate_wpm), "-f", tmp_path, "-o", output_path])
		log_step("Executing macOS say command.")
		subprocess.run(command, check=True)
	finally:
		if os.path.isfile(tmp_path):
			os.remove(tmp_path)


#============================================
def main() -> None:
	"""
	Generate one-voice audio from script text using macOS say.
	"""
	args = parse_args()
	settings, settings_path = pipeline_settings.load_settings(args.settings)
	user = pipeline_settings.get_github_username(settings, "vosslab")
	default_voice = pipeline_settings.get_setting_str(settings, ["tts", "say", "voice"], "")
	default_rate_wpm = pipeline_settings.get_setting_int(
		settings,
		["tts", "say", "rate_wpm"],
		185,
	)
	script_arg = pipeline_settings.resolve_user_scoped_out_path(
		args.script,
		DEFAULT_SCRIPT_PATH,
		user,
	)
	output_arg = pipeline_settings.resolve_user_scoped_out_path(
		args.output,
		DEFAULT_OUTPUT_PATH,
		user,
	)

	requested_voice = default_voice if args.voice is None else args.voice
	rate_wpm = default_rate_wpm if args.rate_wpm is None else args.rate_wpm
	if rate_wpm < 80:
		raise RuntimeError("rate-wpm must be >= 80")

	log_step(f"Using settings file: {settings_path}")
	if args.list_voices:
		log_step("Listing installed macOS say voices.")
		voices = list_available_say_voices()
		for voice in voices:
			print(voice)
		log_step(f"Listed {len(voices)} voice(s).")
		return

	script_path = os.path.abspath(script_arg)
	output_path = os.path.abspath(output_arg)
	log_step(
		"Starting say audio stage with "
		+ f"script={script_path}, output={output_path}, "
		+ f"requested_voice={requested_voice or 'system_default'}, rate_wpm={rate_wpm}"
	)
	if not os.path.isfile(script_path):
		raise FileNotFoundError(f"Missing script input: {script_path}")

	log_step("Loading script text.")
	with open(script_path, "r", encoding="utf-8") as handle:
		script_text = handle.read()
	lines = parse_script_lines(script_text)
	speakers = get_unique_speakers(lines)
	if speakers:
		log_step(f"Detected {len(speakers)} speaker label(s) in script.")
		if len(speakers) > 1:
			log_step("say backend is single-voice; collapsing all speakers into one narration.")
	else:
		log_step("No ROLE: lines detected; using raw script text as narration.")

	narration = build_single_voice_narration(script_text, lines)
	if not narration:
		raise RuntimeError("Script content is empty after normalization.")

	log_step("Resolving macOS voice.")
	voices = list_available_say_voices()
	resolved_voice = resolve_voice_name(requested_voice, voices)
	if requested_voice.strip().lower() == "siri" and not resolved_voice:
		log_step("No explicit Siri voice detected; using system default say voice.")
	else:
		log_step(f"Resolved voice: {resolved_voice or 'system_default'}")

	output_dir = os.path.dirname(output_path)
	if output_dir:
		os.makedirs(output_dir, exist_ok=True)
	run_say_to_file(
		narration=narration,
		output_path=output_path,
		voice_name=resolved_voice,
		rate_wpm=rate_wpm,
	)
	log_step(f"Wrote audio output: {output_path}")


if __name__ == "__main__":
	main()
