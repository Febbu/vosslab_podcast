#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path
from typing import Any

from common import resolve_run_context


def _speaker_from_role(role: str, characters: dict[str, dict[str, str]], supported: list[str]) -> str:
    role_map = {
        "HOST": "host",
        "ANALYST": "analyst",
        "GUEST": "guest",
        "PRODUCER": "producer",
    }
    character_key = role_map.get(role)
    desired = None
    if character_key and character_key in characters:
        desired = characters[character_key].get("voice")
    if desired in supported:
        return desired
    return supported[0]


def _silence(seconds: float, sample_rate: int):
    import numpy as np

    return np.zeros(int(seconds * sample_rate), dtype=np.float32)


def _generate_qwen_audio(script: dict[str, Any], output_path: Path, model_id: str, language: str) -> None:
    import numpy as np
    import soundfile as sf
    import torch
    from qwen_tts import Qwen3TTSModel

    preferred_device = os.getenv("TTS_DEVICE")
    if preferred_device:
        device = preferred_device
    else:
        device = "mps" if torch.backends.mps.is_available() else "cpu"

    model = Qwen3TTSModel.from_pretrained(
        model_id,
        device_map=device,
        dtype=torch.float32,
    )

    supported_speakers = model.get_supported_speakers()
    if not supported_speakers:
        raise RuntimeError("No supported speakers found in the selected model.")

    segments: list[np.ndarray] = []
    sample_rate: int | None = None

    characters = script.get("characters", {})
    for turn in script.get("turns", []):
        role = turn.get("role", "HOST")
        text = turn.get("text", "").strip()
        if not text:
            continue

        speaker = _speaker_from_role(role, characters, supported_speakers)
        wavs, sr = model.generate_custom_voice(
            text,
            speaker=speaker,
            language=language,
            non_streaming_mode=True,
            do_sample=False,
        )

        wav = wavs[0].astype(np.float32)
        if sample_rate is None:
            sample_rate = sr
        elif sample_rate != sr:
            raise RuntimeError("Sample rate mismatch across generated segments.")

        segments.append(wav)
        segments.append(_silence(0.30, sr))

    if not segments or sample_rate is None:
        raise RuntimeError("No audio segments generated from script.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(output_path, np.concatenate(segments), sample_rate)


def _generate_kokoro_audio(
    script: dict[str, Any],
    output_path: Path,
    kokoro_voice: str,
    kokoro_speed: float,
) -> None:
    try:
        import numpy as np
        import soundfile as sf
        from kokoro import KPipeline
    except ModuleNotFoundError as error:
        raise RuntimeError(
            "Kokoro dependencies are missing. Install with: "
            "pip install kokoro soundfile numpy"
        ) from error

    turns = script.get("turns", [])
    if not turns:
        raise RuntimeError("No script turns found.")

    # Use clean spoken text for natural narration (skip role labels like "HOST:").
    lines = [str(turn.get("text", "")).strip() for turn in turns if str(turn.get("text", "")).strip()]
    if not lines:
        raise RuntimeError("No non-empty turns found to synthesize.")

    text = "\n".join(lines)
    pipeline = KPipeline(lang_code="a")  # American English

    chunks: list[Any] = []
    sample_rate = 24000
    for _, _, audio in pipeline(
        text,
        voice=kokoro_voice,
        speed=kokoro_speed,
        split_pattern=r"\n+",
    ):
        if audio is None:
            continue
        if hasattr(audio, "detach"):
            audio = audio.detach().cpu().numpy()
        chunks.append(np.asarray(audio, dtype=np.float32))

    if not chunks:
        raise RuntimeError("Kokoro returned no audio chunks.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(output_path, np.concatenate(chunks), sample_rate)


def _available_apple_voices() -> set[str]:
    proc = subprocess.run(["say", "-v", "?"], capture_output=True, text=True, check=True)
    voices: set[str] = set()
    for line in proc.stdout.splitlines():
        parts = line.strip().split()
        if parts:
            voices.add(parts[0])
    return voices


def _resolve_apple_voice(requested_voice: str | None, available_voices: set[str]) -> str:
    if requested_voice and requested_voice in available_voices:
        return requested_voice
    default_voice = os.getenv("APPLE_TTS_VOICE", "Samantha")
    if default_voice in available_voices:
        return default_voice
    if "Samantha" in available_voices:
        return "Samantha"
    return sorted(available_voices)[0]


def _generate_apple_audio(script: dict[str, Any], output_path: Path, apple_voice: str | None = None) -> None:
    turns = script.get("turns", [])
    if not turns:
        raise RuntimeError("No script turns found.")

    available_voices = _available_apple_voices()
    if not available_voices:
        raise RuntimeError("No Apple voices available from `say -v ?`.")

    voice = _resolve_apple_voice(apple_voice, available_voices)
    full_text = "\n".join(
        f"{turn.get('role', 'HOST')}: {str(turn.get('text', '')).strip()}"
        for turn in turns
        if str(turn.get("text", "")).strip()
    ).strip()
    if not full_text:
        raise RuntimeError("No non-empty turns found to synthesize.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["say", "-v", voice, "-o", str(output_path), full_text], check=True)


def _convert_to_mp3(input_path: Path, output_path: Path) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(input_path), str(output_path)],
        check=True,
        capture_output=True,
        text=True,
    )


def _audio_has_duration(path: Path) -> bool:
    proc = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=nw=1:nk=1",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    value = proc.stdout.strip()
    if not value or value == "N/A":
        return False
    try:
        return float(value) > 0
    except ValueError:
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert script artifact into podcast audio.")
    parser.add_argument("--date", dest="run_date", help="Run date in YYYY-MM-DD. Defaults to today.")
    parser.add_argument("--data-dir", default="data", help="Artifact root directory. Default: data")
    parser.add_argument(
        "--engine",
        choices=["qwen", "kokoro", "apple", "dry-run"],
        default="dry-run",
        help="Audio engine to use. Default: dry-run",
    )
    parser.add_argument(
        "--model",
        default="Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice",
        help="Qwen TTS model id.",
    )
    parser.add_argument("--language", default="English", help="Spoken language label for Qwen-TTS.")
    parser.add_argument(
        "--kokoro-voice",
        default="am_puck",
        help="Kokoro voice id (for --engine kokoro). Default: am_puck",
    )
    parser.add_argument(
        "--kokoro-speed",
        type=float,
        default=1.0,
        help="Kokoro speech speed multiplier. Default: 1.0",
    )
    parser.add_argument("--apple-voice", default=None, help="Override Apple say voice (for --engine apple).")
    parser.add_argument("--list-apple-voices", action="store_true", help="List installed Apple voices and exit.")
    parser.add_argument(
        "--mp3",
        action="store_true",
        help="Also generate episode.mp3 using ffmpeg after audio creation.",
    )
    args = parser.parse_args()

    if args.list_apple_voices:
        for voice in sorted(_available_apple_voices()):
            print(voice)
        return

    data_dir = Path(args.data_dir)
    context = resolve_run_context(data_dir, args.run_date)
    script_path = context.run_dir / "script.json"
    output_path = context.run_dir / "episode.wav"

    if not script_path.exists():
        raise FileNotFoundError(f"Missing input: {script_path}. Run step 03 first.")

    script = json.loads(script_path.read_text(encoding="utf-8"))

    if args.engine == "dry-run":
        manifest = {
            "date": context.run_date,
            "engine": args.engine,
            "status": "validated",
            "turn_count": len(script.get("turns", [])),
            "note": "Dry-run completed. Use --engine qwen to synthesize audio.",
        }
        out_path = context.run_dir / "audio_manifest.json"
        out_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        print(f"Wrote {out_path}")
        return

    if args.engine == "qwen":
        _generate_qwen_audio(script=script, output_path=output_path, model_id=args.model, language=args.language)
    elif args.engine == "kokoro":
        _generate_kokoro_audio(
            script=script,
            output_path=output_path,
            kokoro_voice=args.kokoro_voice,
            kokoro_speed=args.kokoro_speed,
        )
    else:
        output_path = context.run_dir / "episode.aiff"
        _generate_apple_audio(script=script, output_path=output_path, apple_voice=args.apple_voice)
        if not _audio_has_duration(output_path):
            raise RuntimeError(
                "Apple TTS produced an audio file with no duration. "
                "Try running the same command directly in your local terminal."
            )

    print(f"Wrote {output_path}")

    if args.mp3:
        mp3_path = context.run_dir / "episode.mp3"
        _convert_to_mp3(output_path, mp3_path)
        print(f"Wrote {mp3_path}")


if __name__ == "__main__":
    main()
