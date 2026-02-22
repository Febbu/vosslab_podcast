#!/usr/bin/env python3
import argparse
import glob
import os
import re
import subprocess
import tempfile
from datetime import datetime

from podlib import audio_utils
from podlib import pipeline_settings


DEFAULT_SCRIPT_PATH = "out/podcast_narration.txt"
DEFAULT_OUTPUT_PATH = "out/narrator_audio.mp3"
DATE_STAMP_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


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
		help="Path to output audio file (.mp3 or .aiff).",
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
def resolve_latest_script(script_path: str) -> str:
	"""
	Fallback to latest dated script file when default path is missing.

	The narration stage writes dated files like podcast_narration-2026-02-22.txt
	but the default path is podcast_narration.txt (no date). Find the latest
	dated match in the same directory.
	"""
	if os.path.isfile(script_path):
		return script_path
	directory = os.path.dirname(script_path)
	# derive glob pattern from base name: podcast_narration.txt -> podcast_narration-*.txt
	basename = os.path.basename(script_path)
	stem, ext = os.path.splitext(basename)
	pattern = os.path.join(directory, f"{stem}-*{ext}")
	candidates = [p for p in glob.glob(pattern) if os.path.isfile(p)]
	if not candidates:
		return script_path
	# return most recently modified
	candidates.sort(key=os.path.getmtime, reverse=True)
	return candidates[0]


#============================================
def local_date_stamp() -> str:
	"""
	Return local-date stamp for filenames.
	"""
	return datetime.now().astimezone().strftime("%Y-%m-%d")


#============================================
def date_stamp_output_path(output_path: str, date_text: str) -> str:
	"""
	Ensure output filename includes one local-date stamp.
	"""
	candidate = (output_path or "").strip() or DEFAULT_OUTPUT_PATH
	candidate = candidate.replace("{date}", date_text)
	directory, filename = os.path.split(candidate)
	if not filename:
		filename = os.path.basename(DEFAULT_OUTPUT_PATH)
	stem, extension = os.path.splitext(filename)
	if not extension:
		extension = ".mp3"
	if DATE_STAMP_RE.search(filename):
		dated_filename = filename
	else:
		dated_filename = f"{stem}-{date_text}{extension}"
	return os.path.join(directory, dated_filename)


#============================================
def run_say_to_file(
	narration: str,
	output_path: str,
	voice_name: str,
	rate_wpm: int,
) -> None:
	"""
	Run macOS say command to synthesize one AIFF audio file.
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
		voices = audio_utils.list_available_say_voices()
		for voice in voices:
			print(voice)
		log_step(f"Listed {len(voices)} voice(s).")
		return

	script_path = os.path.abspath(resolve_latest_script(script_arg))
	date_text = local_date_stamp()
	dated_output = date_stamp_output_path(output_arg, date_text)
	output_path = os.path.abspath(dated_output)
	log_step(
		"Starting say audio stage with "
		+ f"script={script_path}, output={output_path}, "
		+ f"requested_voice={requested_voice or 'system_default'}, rate_wpm={rate_wpm}"
	)
	log_step(f"Using local date stamp for audio filename: {date_text}")
	if not os.path.isfile(script_path):
		raise FileNotFoundError(f"Missing script input: {script_path}")

	log_step("Loading script text.")
	with open(script_path, "r", encoding="utf-8") as handle:
		script_text = handle.read()
	lines = audio_utils.parse_script_lines(script_text)
	speakers = audio_utils.get_unique_speakers(lines)
	if speakers:
		log_step(f"Detected {len(speakers)} speaker label(s) in script.")
		if len(speakers) > 1:
			log_step("say backend is single-voice; collapsing all speakers into one narration.")
	else:
		log_step("No ROLE: lines detected; using raw script text as narration.")

	narration = audio_utils.build_single_voice_narration(script_text, lines)
	if not narration:
		raise RuntimeError("Script content is empty after normalization.")

	log_step("Resolving macOS voice.")
	voices = audio_utils.list_available_say_voices()
	resolved_voice = audio_utils.resolve_voice_name(requested_voice, voices)
	if requested_voice.strip().lower() == "siri" and not resolved_voice:
		log_step("No explicit Siri voice detected; using system default say voice.")
	else:
		log_step(f"Resolved voice: {resolved_voice or 'system_default'}")

	output_dir = os.path.dirname(output_path)
	if output_dir:
		os.makedirs(output_dir, exist_ok=True)

	# determine if MP3 conversion is needed
	wants_mp3 = output_path.lower().endswith(".mp3")
	if wants_mp3:
		# say produces AIFF; convert to MP3 afterward
		aiff_path = output_path.rsplit(".", 1)[0] + ".aiff"
	else:
		aiff_path = output_path

	run_say_to_file(
		narration=narration,
		output_path=aiff_path,
		voice_name=resolved_voice,
		rate_wpm=rate_wpm,
	)
	log_step(f"Wrote AIFF audio: {aiff_path}")

	if wants_mp3:
		log_step("Converting AIFF to MP3 with lame.")
		audio_utils.convert_to_mp3(aiff_path, output_path)
		# clean up intermediate AIFF
		os.remove(aiff_path)
		log_step(f"Wrote MP3 audio: {output_path}")
	else:
		log_step(f"Wrote audio output: {output_path}")


if __name__ == "__main__":
	main()
