"""Audio loading and metadata extraction.

Recorder filenames embed the capture date/time, e.g. ``R20241011-180923.WAV``
maps to 2024-10-11 18:09:23, so no manual renaming is needed.

Field files are often hour-scale WAVs or multi-hour MP3s; ``load_audio_segment``
seeks with ffmpeg so we never hold the whole recording in RAM.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

import numpy as np

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


def audio_duration_s(path: str | Path) -> float:
    """Duration in seconds without decoding the whole file when possible."""
    path = Path(path)
    try:
        import soundfile as sf

        with sf.SoundFile(str(path)) as fh:
            return float(len(fh) / fh.samplerate)
    except Exception:
        pass
    ffprobe = shutil.which("ffprobe")
    if ffprobe:
        try:
            out = subprocess.check_output(
                [
                    ffprobe,
                    "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    str(path),
                ],
                stderr=subprocess.STDOUT,
                text=True,
            )
            return float(out.strip())
        except (subprocess.CalledProcessError, ValueError):
            pass
    import librosa

    return float(librosa.get_duration(path=str(path)))


def load_audio(path: str | Path, sample_rate: int) -> tuple[np.ndarray, int]:
    """Load one audio file as mono at the requested sample rate."""
    return load_audio_segment(path, sample_rate, offset_s=0.0, duration_s=None)


def load_audio_segment(
    path: str | Path,
    sample_rate: int,
    offset_s: float = 0.0,
    duration_s: float | None = None,
) -> tuple[np.ndarray, int]:
    """Load a time slice as mono float32.

    Prefers ffmpeg (fast seek, supports ``.m4a``). Falls back to librosa.
    """
    path = Path(path)
    y = _load_via_ffmpeg(path, sample_rate, offset_s, duration_s)
    if y is not None:
        return y, sample_rate
    import librosa

    kwargs: dict[str, float] = {"offset": offset_s}
    if duration_s is not None:
        kwargs["duration"] = duration_s
    y, sr = librosa.load(str(path), sr=sample_rate, mono=True, **kwargs)
    return y.astype(np.float32), sr


def _load_via_ffmpeg(
    path: Path,
    sample_rate: int,
    offset_s: float,
    duration_s: float | None,
) -> np.ndarray | None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return None
    cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin"]
    if offset_s > 0:
        cmd.extend(["-ss", f"{offset_s:.3f}"])
    cmd.extend(["-i", str(path)])
    if duration_s is not None:
        cmd.extend(["-t", f"{duration_s:.3f}"])
    cmd.extend(["-ac", "1", "-ar", str(sample_rate), "-f", "f32le", "pipe:1"])
    try:
        raw = subprocess.check_output(cmd, stderr=subprocess.DEVNULL)
    except (subprocess.CalledProcessError, OSError):
        return None
    if not raw:
        return np.zeros(0, dtype=np.float32)
    return np.frombuffer(raw, dtype=np.float32).copy()
