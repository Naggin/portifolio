"""Audio loading and metadata extraction.

Recorder filenames embed the capture date/time, e.g. ``R20241011-180923.WAV``
maps to 2024-10-11 18:09:23, so no manual renaming is needed.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

import librosa
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


def load_audio(path: str | Path, sample_rate: int) -> tuple[np.ndarray, int]:
    """Load an audio file as mono at the requested sample rate."""
    y, sr = librosa.load(str(path), sr=sample_rate, mono=True)
    return y.astype(np.float32), sr
