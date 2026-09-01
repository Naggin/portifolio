"""Tests for Phase 2 calibration using the synthetic reference.

The synthetic sample places tonal calls around 2.6–3.4 kHz on top of strong
80/150 Hz wind. Calibration must lock onto the call band and never onto wind.
"""

from __future__ import annotations

import sys
from pathlib import Path

from bioacoustics.calibration import CalibrationConfig, analyze_reference
from bioacoustics.config import DetectionConfig

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from generate_sample import synthesize  # noqa: E402


def _analyze(seed: int = 42):
    cfg = CalibrationConfig()
    audio = synthesize(sr=cfg.sample_rate, duration_s=30.0, seed=seed)
    return analyze_reference(audio, cfg), cfg


def test_peak_is_in_call_band_not_wind():
    result, _ = _analyze()
    # Dominant peak should sit in the synthetic call band, far above wind.
    assert 2400.0 <= result.peak_freq_hz <= 3600.0
    assert result.peak_freq_hz > 300.0


def test_recommended_band_covers_calls_and_excludes_wind():
    result, _ = _analyze()
    # Lowcut clears the wind floor but stays well below the call peak.
    assert 1800.0 <= result.recommended_lowcut_hz <= 2500.0
    # Highcut sits above the higher-pitched duet individual (~3.3 kHz).
    assert 3400.0 <= result.recommended_highcut_hz <= 4200.0
    assert result.recommended_highcut_hz > result.recommended_lowcut_hz


def test_recommended_threshold_k_within_bounds():
    result, cfg = _analyze()
    lo, hi = cfg.threshold_k_bounds
    assert lo <= result.recommended_threshold_k <= hi


def test_recommended_config_is_usable_and_detects_calls():
    result, _ = _analyze()
    cfg = result.recommended_config()
    assert isinstance(cfg, DetectionConfig)

    from bioacoustics.detection import run_detection

    audio = synthesize(sr=cfg.sample_rate, duration_s=30.0)
    detection = run_detection(audio, cfg)
    # The 7 solo chirps + 1 duet remain detectable with the calibrated band.
    assert detection.n_events == 8


def test_config_roundtrip_from_calibration_json(tmp_path):
    from bioacoustics.calibration import write_calibration_json

    result, cfg = _analyze()
    js = write_calibration_json(result, cfg, tmp_path / "calibration.json")
    loaded = DetectionConfig.from_json(js)
    assert loaded.lowcut_hz == result.recommended_lowcut_hz
    assert loaded.highcut_hz == result.recommended_highcut_hz
    assert abs(loaded.threshold_k - round(result.recommended_threshold_k, 2)) < 1e-6
