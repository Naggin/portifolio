"""JSON report contract used by the React dashboard."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bioacoustics.config import DetectionConfig
from bioacoustics.pipeline import PipelineResult, process_file
from bioacoustics.report import build_report_payload, write_json_report
from generate_sample import synthesize
import soundfile as sf


def _write_sample(tmp_path: Path, name: str = "R20241011-180923.WAV") -> Path:
    cfg = DetectionConfig()
    audio = synthesize(sr=cfg.sample_rate, duration_s=30.0, seed=42)
    path = tmp_path / name
    sf.write(str(path), audio, cfg.sample_rate, subtype="PCM_16")
    return path


def test_json_report_shape(tmp_path: Path):
    path = _write_sample(tmp_path)
    result = process_file(path)
    payload = build_report_payload([result])

    assert payload["species"] == "Sphaenorhynchus caramaschii"
    assert payload["summary"]["n_files"] == 1
    assert payload["summary"]["n_events"] == 8
    assert payload["summary"]["max_simultaneous"] == 2
    assert len(payload["files"]) == 1
    assert payload["files"][0]["file"] == path.name
    assert payload["files"][0]["recorded_at"] == "2024-10-11T18:09:23"
    assert payload["files"][0]["spectrogram"] == "R20241011-180923_spectrogram.png"
    assert len(payload["events"]) == 8
    assert payload["events"][0].keys() >= {
        "file", "event", "start_s", "end_s", "peak_time_s", "peak_freq_hz", "n_callers",
    }
    assert len(payload["by_hour"]) == 24
    assert payload["by_hour"][18]["n_events"] == 8
    assert len(payload["by_month"]) == 12
    assert payload["by_month"][9]["n_events"] == 8  # October is month 10, 0-indexed as 9


def test_write_json_report_roundtrip(tmp_path: Path):
    path = _write_sample(tmp_path)
    result = process_file(path)
    out = write_json_report([result], tmp_path / "resultado.json")
    loaded = json.loads(out.read_text())
    assert loaded["summary"]["n_events"] == 8
    assert loaded["config"]["lowcut_hz"] == 1500.0
