#!/usr/bin/env python3
import json
import os
from pathlib import Path
from typing import Dict, List

import numpy as np
import soundfile as sf
import torch
from qwen_tts import Qwen3TTSModel


def _load_voice_config(path: Path) -> Dict[str, str | None]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _parse_script_lines(script_text: str) -> List[tuple[str, str]]:
    lines = []
    for raw in script_text.splitlines():
        raw = raw.strip()
        if not raw:
            continue
        if ":" not in raw:
            continue
        role, text = raw.split(":", 1)
        role = role.strip().upper()
        text = text.strip()
        if not text:
            continue
        lines.append((role, text))
    return lines


def _pick_speaker(
    role: str,
    voices: Dict[str, str | None],
    supported: List[str],
) -> str:
    if role == "HOST":
        desired = voices.get("host_voice")
    elif role == "ANALYST":
        desired = voices.get("analyst_voice")
    elif role == "GUEST":
        desired = voices.get("guest_voice_override") or voices.get("guest_voice")
    else:
        desired = None

    if desired in supported:
        return desired
    return supported[0]


def _silence(seconds: float, sample_rate: int) -> np.ndarray:
    length = int(seconds * sample_rate)
    return np.zeros(length, dtype=np.float32)


def main() -> None:
    script_path = Path(os.getenv("SCRIPT_PATH", "out/script.txt"))
    output_path = Path(os.getenv("OUTPUT_AUDIO", "out/episode.wav"))
    voices_path = Path(os.getenv("VOICES_PATH", "voices.json"))
    model_id = os.getenv("QWEN_TTS_MODEL", "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice")
    language = os.getenv("TTS_LANGUAGE", "English")

    if not script_path.exists():
        raise FileNotFoundError(f"Missing script: {script_path}")
    if not voices_path.exists():
        raise FileNotFoundError(f"Missing voices config: {voices_path}")

    script_text = script_path.read_text(encoding="utf-8")
    lines = _parse_script_lines(script_text)
    if not lines:
        raise RuntimeError("No valid ROLE: text lines found in script.")

    preferred_device = os.getenv("TTS_DEVICE")
    if preferred_device:
        device = preferred_device
    else:
        device = "mps" if torch.backends.mps.is_available() else "cpu"

    # Float32 is more stable than float16 on some Apple Silicon TTS runs.
    dtype = torch.float32

    model = Qwen3TTSModel.from_pretrained(
        model_id,
        device_map=device,
        dtype=dtype,
    )
    supported_speakers = model.get_supported_speakers()
    if not supported_speakers:
        raise RuntimeError("No supported speakers found for this model.")

    voices = _load_voice_config(voices_path)

    segments: List[np.ndarray] = []
    sample_rate = None
    for role, text in lines:
        speaker = _pick_speaker(role, voices, supported_speakers)
        wavs, sr = model.generate_custom_voice(
            text,
            speaker=speaker,
            language=language,
            non_streaming_mode=True,
            do_sample=False,
        )
        wav = wavs[0]
        if sample_rate is None:
            sample_rate = sr
        elif sample_rate != sr:
            raise RuntimeError("Sample rate mismatch between segments.")
        segments.append(wav.astype(np.float32))
        segments.append(_silence(0.35, sr))

    if sample_rate is None:
        raise RuntimeError("No audio generated.")

    full_audio = np.concatenate(segments)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(output_path, full_audio, sample_rate)
    print(f"Wrote {output_path}")


if __name__ == "__main__":
    main()
