"""Peak-window spectrograms must cover where calls actually are, not t=0."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bioacoustics.config import DetectionConfig  # noqa: E402
from bioacoustics.detection import CallEvent  # noqa: E402
from bioacoustics.pipeline import process_file  # noqa: E402
from bioacoustics.visualization import (  # noqa: E402
    EVENT_CONTEXT_PAD_S,
    densest_window_start,
    event_context_window,
    event_spectrogram_title,
    loudest_event_in_window,
    save_event_spectrogram,
    save_file_spectrograms,
    save_spectrogram_window,
)
from generate_sample import _chirp  # noqa: E402


def _ev(t: float, energy: float = 1.0) -> CallEvent:
    return CallEvent(
        start_s=t,
        end_s=t + 0.1,
        peak_time_s=t,
        peak_freq_hz=2900.0,
        energy=energy,
        n_callers=1,
    )


def test_densest_window_start_prefers_late_cluster():
    events = [_ev(t) for t in (1.0, 2.0, 70.0, 70.2, 70.4, 70.6)]
    assert densest_window_start(events, 10.0) == pytest.approx(70.0)
    assert densest_window_start([], 60.0) == 0.0
    # Clamp so a 60 s window stays inside a 90 s file.
    assert densest_window_start(events, 60.0, duration_s=90.0) == pytest.approx(30.0)


def test_loudest_event_in_window():
    events = [_ev(10.0, 1.0), _ev(12.0, 9.0), _ev(80.0, 50.0)]
    got = loudest_event_in_window(events, 8.0, 20.0)
    assert got is not None
    assert got.peak_time_s == pytest.approx(12.0)
    assert loudest_event_in_window(events, 0.0, 5.0) is None


def _late_call_wav(path: Path, cfg: DetectionConfig, duration_s: float = 90.0) -> list[float]:
    """Wind + hiss everywhere; species-like chirps only after ~70 s."""
    sr = cfg.sample_rate
    n = int(sr * duration_s)
    rng = np.random.default_rng(0)
    t_full = np.arange(n) / sr
    audio = (
        0.35 * np.sin(2 * np.pi * 80 * t_full)
        + 0.2 * np.sin(2 * np.pi * 150 * t_full)
        + 0.01 * rng.standard_normal(n)
    ).astype(np.float32)
    centers = [72.0, 75.0, 78.0, 81.0, 84.0]
    for center in centers:
        start = int(center * sr)
        length = int(0.25 * sr)
        if start < 0 or start + length > n:
            continue
        t = np.arange(length) / sr
        audio[start : start + length] += _chirp(t, 2600, 2800, 0.55).astype(np.float32)
    peak = float(np.max(np.abs(audio))) or 1.0
    audio = (audio / peak * 0.9).astype(np.float32)
    sf.write(str(path), audio, sr, subtype="PCM_16")
    return centers


def test_densest_window_spectrogram_covers_late_calls_not_t0(tmp_path: Path):
    cfg = DetectionConfig(
        chunk_duration_s=30.0,
        chunk_overlap_s=3.0,
        edge_guard_s=1.5,
        use_noise_reduction=False,
        spectrogram_preview_s=60.0,
    )
    wav = tmp_path / "R20241012-041002.WAV"
    centers = _late_call_wav(wav, cfg, duration_s=90.0)

    result = process_file(wav, cfg)
    peaks = [e.peak_time_s for e in result.detection.events]
    assert peaks, "expected late synthetic calls to be detected"
    assert min(peaks) > 60.0
    assert all(abs(p - c) < 1.5 for p, c in zip(sorted(peaks), centers)) or min(peaks) > 65.0

    t0 = densest_window_start(
        result.detection.events, cfg.spectrogram_preview_s, result.detection.duration_s
    )
    assert t0 > 0.0
    assert t0 + cfg.spectrogram_preview_s >= min(peaks)
    # Old behaviour (first 60 s) would start at 0 and miss every call.
    assert t0 + 1.0 > 1.0  # window is not pinned to the file start in a useless way
    assert min(peaks) <= t0 + cfg.spectrogram_preview_s

    written = save_file_spectrograms(
        wav,
        result.detection.events,
        result.detection.duration_s,
        cfg,
        tmp_path,
        result=result.detection,
    )
    main = next(item for item in written if item.path.name.endswith("_spectrogram.png"))
    assert main.path.is_file() and main.path.stat().st_size > 0
    assert main.t0 > 0.0
    assert main.t0 + main.duration_s >= min(peaks)
    assert main.n_marked >= 1
    # First-60 s preview would have t0≈0 and t1≤60, excluding the chirps.
    assert main.t0 + main.duration_s > 70.0

    zoom = [item for item in written if item.kind == "zoom"]
    assert zoom
    assert zoom[0].path.is_file()
    assert 70.0 <= zoom[0].t0 + zoom[0].duration_s
    assert zoom[0].duration_s == pytest.approx(8.0, abs=0.3)


def test_save_spectrogram_window_marks_given_events_not_recount(tmp_path: Path):
    cfg = DetectionConfig(use_noise_reduction=False)
    wav = tmp_path / "clip.wav"
    sr = cfg.sample_rate
    n = int(sr * 12.0)
    rng = np.random.default_rng(1)
    audio = (0.02 * rng.standard_normal(n)).astype(np.float32)
    sf.write(str(wav), audio, sr, subtype="PCM_16")
    # Pretend the batch only found one peak at 8 s; do not re-count.
    fake = [_ev(8.0, energy=3.0)]
    out = tmp_path / "window.png"
    written = save_spectrogram_window(
        wav, fake, t0=4.0, duration_s=6.0, cfg=cfg, out_path=out, title="teste"
    )
    assert written.path.is_file()
    assert written.t0 == pytest.approx(4.0)
    assert written.n_marked == 1


def test_event_context_window_pads_and_clamps():
    t0, dur = event_context_window(2.276, 2.368, 3600.0)
    assert t0 == pytest.approx(2.276 - EVENT_CONTEXT_PAD_S)
    assert (t0 + dur) == pytest.approx(2.368 + EVENT_CONTEXT_PAD_S)
    t0, dur = event_context_window(0.10, 0.20, 10.0)
    assert t0 == pytest.approx(0.0)
    assert dur == pytest.approx(0.20 + EVENT_CONTEXT_PAD_S)
    t0, dur = event_context_window(9.80, 9.90, 10.0)
    assert t0 + dur == pytest.approx(10.0)
    t0, dur = event_context_window(0.0, 60.0, 120.0, peak_time_s=10.0, max_window_s=8.0)
    assert dur == pytest.approx(8.0)
    assert t0 == pytest.approx(6.0)


def test_event_spectrogram_title_is_not_individuo():
    title = event_spectrogram_title("R20241011-180923.WAV", 1, 2.299, 2713.2, 1)
    assert "indivíduo" not in title.lower()
    assert "individuo" not in title.lower()
    assert "cantores simultâneos estimados: 1" in title
    assert "evento 1" in title
    assert "2713" in title


def test_save_event_spectrogram_uses_row_peak_and_file_absolute_time(tmp_path: Path):
    cfg = DetectionConfig(use_noise_reduction=False)
    wav = tmp_path / "R20241011-180923.WAV"
    sr = cfg.sample_rate
    duration_s = 6.0
    n = int(sr * duration_s)
    t = np.arange(n) / sr
    audio = (0.01 * np.random.default_rng(2).standard_normal(n)).astype(np.float32)
    tone = (t >= 2.20) & (t < 2.40)
    audio[tone] += (0.4 * np.sin(2 * np.pi * 2713.0 * t[tone])).astype(np.float32)
    sf.write(str(wav), audio, sr, subtype="PCM_16")
    event = CallEvent(
        start_s=2.276,
        end_s=2.368,
        peak_time_s=2.299,
        peak_freq_hz=2713.2,
        energy=1.0,
        n_callers=1,
    )
    out = tmp_path / "event.png"
    written = save_event_spectrogram(
        wav, event, cfg, out, filename="R20241011-180923.WAV", event_n=1
    )
    assert written.path.is_file() and written.path.stat().st_size > 2000
    assert written.kind == "event"
    assert written.n_marked == 1
    assert written.t0 == pytest.approx(2.276 - EVENT_CONTEXT_PAD_S, abs=0.05)
    assert written.t0 + written.duration_s > 2.368
    # Context of a few seconds, not the 0.09 s call sliver.
    assert written.duration_s > 2.0
