"""Audio loading and metadata extraction.

Recorder filenames embed the capture date/time, e.g. ``R20241011-180923.WAV``
maps to 2024-10-11 18:09:23, so no manual renaming is needed.
"""

from __future__ import annotations

import io
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf

_FILENAME_RE = re.compile(r"R?(\d{8})[-_](\d{6})", re.IGNORECASE)


def parse_recording_datetime(path: str | Path) -> datetime | None:
    """Extract the capture datetime encoded in a recorder filename.

    Returns ``None`` if the filename does not match the expected pattern.
    """
    stem = Path(path).stem
    match = _FILENAME_RE.search(stem)
    if not match:
        return None
    date_part, time_part = match.groups()
    try:
        return datetime.strptime(date_part + time_part, "%Y%m%d%H%M%S")
    except ValueError:
        return None


def load_audio(path: str | Path, sample_rate: int) -> tuple[np.ndarray, int]:
    """Load an audio file as mono at the requested sample rate.

    librosa's soundfile backend covers WAV/FLAC/OGG/MP3 but not AAC/m4a; those
    are decoded via a small ffmpeg fallback so field recordings in .m4a work.
    """
    try:
        y, sr = librosa.load(str(path), sr=sample_rate, mono=True)
        return y.astype(np.float32), sr
    except Exception:
        return _load_via_ffmpeg(path, sample_rate)


def _load_via_ffmpeg(path: str | Path, sample_rate: int) -> tuple[np.ndarray, int]:
    """Decode any ffmpeg-readable file (e.g. .m4a) to mono float32 audio."""
    if shutil.which("ffmpeg") is None:
        raise RuntimeError(
            f"Cannot decode {path!r}: unsupported by libsndfile and ffmpeg is not "
            "installed. Install ffmpeg or convert the file to WAV/FLAC."
        )
    cmd = [
        "ffmpeg", "-v", "error", "-i", str(path),
        "-ac", "1", "-ar", str(sample_rate), "-f", "wav", "pipe:1",
    ]
    proc = subprocess.run(cmd, capture_output=True, check=True)
    y, sr = sf.read(io.BytesIO(proc.stdout), dtype="float32")
    if y.ndim > 1:
        y = y.mean(axis=1)
    return y.astype(np.float32), sr
