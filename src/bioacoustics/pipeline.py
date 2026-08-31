"""Single-file orchestration of the detection pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .audio_io import load_audio, parse_recording_datetime
from .config import DetectionConfig
from .detection import DetectionResult, run_detection


@dataclass
class PipelineResult:
    path: Path
    filename: str
    recorded_at: datetime | None
    detection: DetectionResult


def process_file(path: str | Path, cfg: DetectionConfig | None = None) -> PipelineResult:
    """Load one recording and run the full detection pipeline on it."""
    cfg = cfg or DetectionConfig()
    path = Path(path)
    y, _ = load_audio(path, cfg.sample_rate)
    detection = run_detection(y, cfg)
    return PipelineResult(
        path=path,
        filename=path.name,
        recorded_at=parse_recording_datetime(path),
        detection=detection,
    )
