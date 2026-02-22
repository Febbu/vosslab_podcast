#!/usr/bin/env python3
import argparse
import json
import os
from datetime import datetime

import numpy
import soundfile
import torch
from qwen_tts import Qwen3TTSModel


#============================================
def log_step(message: str) -> None:
	"""
	Print one timestamped progress line.
	"""
	now_text = datetime.now().strftime("%H:%M:%S")
	print(f"[script_to_audio {now_text}] {message}", flush=True)


#============================================
def parse_args() -> argparse.Namespace:
	"""
	Parse command-line arguments.
	"""
	parser = argparse.ArgumentParser(
		description="Convert an N-speaker podcast script into audio."
	)
	parser.add_argument(
		"--script",
		default="out/podcast_script.txt",
		help="Path to speaker script text file.",
	)
	parser.add_argument(
		"--output",
		default="out/episode.wav",
		help="Path to output WAV audio file.",
	)
	parser.add_argument(
		"--voices",
		default="voices.json",
		help="Optional voice config JSON path.",
	)
	parser.add_argument(
		"--model-id",
		default="Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice",
		help="Qwen TTS model id.",
	)
	parser.add_argument(
		"--language",
		default="English",
		help="TTS language value passed to the model.",
	)
	parser.add_argument(
		"--device",
		default="",
		help="Optional explicit TTS device. Default prefers MPS then CPU.",
	)
	parser.add_argument(
		"--pause-seconds",
		type=float,
		default=0.35,
		help="Silence between generated speaker segments.",
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
def ordered_unique_speakers(lines: list[tuple[str, str]]) -> list[str]:
	"""
	Return speakers in first-seen order.
	"""
	labels = []
	for speaker, _text in lines:
		if speaker not in labels:
			labels.append(speaker)
	return labels


#============================================
def load_voice_config(path: str) -> dict:
	"""
	Load optional voice configuration JSON.
	"""
	if not os.path.isfile(path):
		return {}
	with open(path, "r", encoding="utf-8") as handle:
		config = json.load(handle)
	return config


#============================================
def choose_voice_device(device_arg: str) -> str:
	"""
	Resolve runtime device for TTS inference.
	"""
	if device_arg:
		return device_arg
	if torch.backends.mps.is_available():
		return "mps"
	return "cpu"


#============================================
def silence(seconds: float, sample_rate: int) -> numpy.ndarray:
	"""
	Create a float32 silent audio segment.
	"""
	length = int(seconds * sample_rate)
	return numpy.zeros(length, dtype=numpy.float32)


#============================================
def derive_config_voice(
	label: str,
	config: dict,
) -> str:
	"""
	Resolve preferred voice from config keys.
	"""
	speaker_map = config.get("speaker_map") or {}
	if not isinstance(speaker_map, dict):
		speaker_map = {}
	for key in (label, label.upper(), label.lower()):
		if key in speaker_map:
			return str(speaker_map[key])

	legacy_map = {
		"SPEAKER_1": config.get("host_voice"),
		"SPEAKER_2": config.get("analyst_voice"),
		"SPEAKER_3": config.get("guest_voice_override") or config.get("guest_voice"),
		"HOST": config.get("host_voice"),
		"ANALYST": config.get("analyst_voice"),
		"GUEST": config.get("guest_voice_override") or config.get("guest_voice"),
	}
	value = legacy_map.get(label)
	if value:
		return str(value)
	return ""


#============================================
def build_speaker_voice_map(
	speakers: list[str],
	config: dict,
	supported_speakers: list[str],
) -> dict[str, str]:
	"""
	Build deterministic mapping from script speakers to model speakers.
	"""
	if not supported_speakers:
		raise RuntimeError("No supported model speakers available.")
	mapping: dict[str, str] = {}
	for index, speaker in enumerate(speakers):
		desired = derive_config_voice(speaker, config)
		if desired in supported_speakers:
			mapping[speaker] = desired
			continue
		fallback = supported_speakers[index % len(supported_speakers)]
		mapping[speaker] = fallback
	return mapping


#============================================
def main() -> None:
	"""
	Generate one WAV file from an N-speaker podcast script.
	"""
	args = parse_args()
	log_step(
		"Starting audio stage with "
		+ f"script={os.path.abspath(args.script)}, output={os.path.abspath(args.output)}, "
		+ f"voices={os.path.abspath(args.voices)}, model_id={args.model_id}"
	)
	script_path = os.path.abspath(args.script)
	if not os.path.isfile(script_path):
		raise FileNotFoundError(f"Missing script file: {script_path}")

	log_step("Loading podcast script file.")
	with open(script_path, "r", encoding="utf-8") as handle:
		script_text = handle.read()
	lines = parse_script_lines(script_text)
	if not lines:
		raise RuntimeError("No valid SPEAKER: text lines found in script.")
	log_step(f"Parsed {len(lines)} speaker line(s) from script.")

	device = choose_voice_device(args.device)
	log_step(f"Loading TTS model on device: {device}")
	model = Qwen3TTSModel.from_pretrained(
		args.model_id,
		device_map=device,
		dtype=torch.float32,
	)
	supported_speakers = model.get_supported_speakers()
	log_step(f"Model supports {len(supported_speakers)} speaker voice(s).")
	script_speakers = ordered_unique_speakers(lines)
	log_step(f"Script uses {len(script_speakers)} unique speaker label(s).")
	config = load_voice_config(args.voices)
	log_step("Building speaker-to-voice map.")
	speaker_map = build_speaker_voice_map(
		script_speakers,
		config,
		supported_speakers,
	)
	for speaker in speaker_map:
		log_step(f"Voice map: {speaker} -> {speaker_map[speaker]}")

	segments = []
	sample_rate = None
	for index, (speaker, text) in enumerate(lines, start=1):
		model_speaker = speaker_map[speaker]
		log_step(
			f"Generating audio for line {index}/{len(lines)}: "
			+ f"speaker={speaker}, chars={len(text)}"
		)
		wavs, rate = model.generate_custom_voice(
			text,
			speaker=model_speaker,
			language=args.language,
			non_streaming_mode=True,
			do_sample=False,
		)
		segment = wavs[0].astype(numpy.float32)
		if sample_rate is None:
			sample_rate = rate
		if sample_rate != rate:
			raise RuntimeError("Sample rate mismatch between generated segments.")
		segments.append(segment)
		segments.append(silence(args.pause_seconds, rate))
		log_step(f"Generated segment {index}; samples={len(segment)}, sample_rate={rate}")

	if sample_rate is None:
		raise RuntimeError("TTS returned no audio segments.")

	log_step("Concatenating generated segments into final waveform.")
	audio = numpy.concatenate(segments)
	output_path = os.path.abspath(args.output)
	os.makedirs(os.path.dirname(output_path), exist_ok=True)
	log_step(f"Writing WAV output to {output_path}")
	soundfile.write(output_path, audio, sample_rate)
	log_step(f"Wrote {output_path}; total_samples={len(audio)}, sample_rate={sample_rate}")


if __name__ == "__main__":
	main()
