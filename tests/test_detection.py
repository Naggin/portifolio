"""Sanity tests for the detection pipeline using synthetic audio.

These lock in the core Phase 1 behaviour: solo calls are detected with correct
timestamps, wind does not create false positives, and a two-individual duet is
counted as two simultaneous callers.
"""

from __future__ import annotations

import numpy as np

from bioacoustics.config import DetectionConfig
from bioacoustics.detection import run_detection

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from generate_sample import synthesize  # noqa: E402


def _synthetic_cfg() -> DetectionConfig:
    """Band matching the synthetic fixture (chirps at 2.6–2.8 & 3.2–3.4 kHz).

    The shipped defaults are calibrated to the real species band (~2.2–3.2 kHz);
    the synthetic generator predates that and was built around the wider generic
    1.5–4 kHz band, so these algorithm tests pin that band explicitly to stay
    independent of the species default.
    """
    cfg = DetectionConfig()
    cfg.lowcut_hz = 1_500.0
    cfg.highcut_hz = 4_000.0
    return cfg


def _detect(seed: int = 42):
    cfg = _synthetic_cfg()
    audio = synthesize(sr=cfg.sample_rate, duration_s=30.0, seed=seed)
    return run_detection(audio, cfg), cfg


def test_detects_expected_number_of_calls():
    result, _ = _detect()
    # 7 solo chirps + 1 duet event = 8 events.
    assert result.n_events == 8


def test_calls_land_near_expected_times():
    result, _ = _detect()
    expected = [2.0, 5.0, 8.5, 12.0, 15.0, 20.0, 24.0, 27.5]
    peak_times = sorted(e.peak_time_s for e in result.events)
    assert len(peak_times) == len(expected)
    for got, exp in zip(peak_times, expected):
        assert abs(got - exp) < 0.5, f"call at {got:.2f}s expected near {exp}s"


def test_calls_fall_within_species_band():
    result, cfg = _detect()
    for e in result.events:
        assert cfg.lowcut_hz <= e.peak_freq_hz <= cfg.highcut_hz


def test_detects_two_simultaneous_individuals():
    result, _ = _detect()
    assert result.max_simultaneous == 2
    # The duet occurs around 15 s.
    duet = [e for e in result.events if abs(e.peak_time_s - 15.0) < 0.6]
    assert duet and duet[0].n_callers == 2


def test_no_false_positive_on_pure_wind():
    cfg = DetectionConfig()
    rng = np.random.default_rng(0)
    n = int(cfg.sample_rate * 10)
    t = np.arange(n) / cfg.sample_rate
    wind = 0.4 * np.sin(2 * np.pi * 90 * t) + 0.2 * np.sin(2 * np.pi * 150 * t)
    wind += 0.01 * rng.standard_normal(n)
    result = run_detection(wind.astype(np.float32), cfg)
    assert result.n_events == 0
