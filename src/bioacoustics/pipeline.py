"""Single-file orchestration of the detection pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np

from .audio_io import audio_duration_s, load_audio, load_audio_segment, parse_recording_datetime
from .config import DetectionConfig
from .detection import DetectionResult, count_max_simultaneous, run_detection


@dataclass
class PipelineResult:
    path: Path
    filename: str
    recorded_at: datetime | None
    detection: DetectionResult


def process_file(path: str | Path, cfg: DetectionConfig | None = None) -> PipelineResult:
    """Load one recording and run the full detection pipeline on it.

    Files longer than ``cfg.chunk_duration_s`` are processed in overlapping
    windows so hour-scale field WAVs/MP3s fit in memory.
    """
    cfg = cfg or DetectionConfig()
    path = Path(path)
    duration = audio_duration_s(path)
    if duration <= cfg.chunk_duration_s:
        y, _ = load_audio(path, cfg.sample_rate)
        detection = run_detection(y, cfg)
    else:
        detection = _process_chunked(path, cfg, duration)
    return PipelineResult(
        path=path,
        filename=path.name,
        recorded_at=parse_recording_datetime(path),
        detection=detection,
    )


def _process_chunked(path: Path, cfg: DetectionConfig, duration_s: float) -> DetectionResult:
    overlap = max(cfg.chunk_overlap_s, 2.0 * cfg.edge_guard_s)
    hop = max(cfg.chunk_duration_s - overlap, cfg.edge_guard_s + 0.1)
    events = []
    energy_parts: list[np.ndarray] = []
    time_parts: list[np.ndarray] = []
    preview: DetectionResult | None = None
    start = 0.0
    chunk_index = 0
    while start < duration_s - 1e-6:
        length = min(cfg.chunk_duration_s, duration_s - start)
        y, _ = load_audio_segment(path, cfg.sample_rate, offset_s=start, duration_s=length)
        if y.size == 0:
            break
        chunk = run_detection(y, cfg)
        is_first = chunk_index == 0
        is_last = (start + length) >= duration_s - 1e-3
        # run_detection already drops ``edge_guard_s`` at each chunk edge.
        # Keep those interior events; hop == 2*guard so windows abut, no dupes.
        for ev in chunk.events:
            events.append(
                type(ev)(
                    start_s=ev.start_s + start,
                    end_s=ev.end_s + start,
                    peak_time_s=ev.peak_time_s + start,
                    peak_freq_hz=ev.peak_freq_hz,
                    energy=ev.energy,
                    n_callers=ev.n_callers,
                )
            )
        lo = 0.0 if is_first else cfg.edge_guard_s
        hi = length if is_last else length - cfg.edge_guard_s
        keep = (chunk.times >= lo) & (chunk.times < hi)
        if np.any(keep):
            energy_parts.append(np.asarray(chunk.band_energy)[keep])
            time_parts.append(np.asarray(chunk.times)[keep] + start)
        # First-chunk STFT is kept only so DetectionResult still has a
        # spectrogram matrix; PNG validation reloads the densest peak window.
        if preview is None:
            preview = chunk
        chunk_index += 1
        start += hop

    if preview is None:
        empty, _ = load_audio_segment(path, cfg.sample_rate, 0.0, min(1.0, duration_s))
        return run_detection(empty, cfg)

    times = np.concatenate(time_parts) if time_parts else preview.times
    band_energy = np.concatenate(energy_parts) if energy_parts else preview.band_energy
    return DetectionResult(
        events=events,
        max_simultaneous=count_max_simultaneous(events, cfg),
        duration_s=float(duration_s),
        spectrogram_db=preview.spectrogram_db,
        freqs=preview.freqs,
        times=times,
        band_energy=band_energy,
        threshold=float(preview.threshold),
        preview_times=preview.times,
    )
