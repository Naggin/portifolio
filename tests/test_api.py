"""HTTP API: upload limits, analyze, and existing report endpoints."""

from __future__ import annotations

import io
import json
import sys
import threading
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlencode

import numpy as np
import pytest
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bioacoustics import api  # noqa: E402
from bioacoustics.config import DetectionConfig  # noqa: E402


def _wav_bytes(duration_s: float = 4.0, sr: int = 22_050) -> bytes:
    """Tiny in-band tone; long enough for the pipeline filters, far smaller than field WAVs."""
    n = int(sr * duration_s)
    t = np.arange(n) / sr
    audio = (0.05 * np.sin(2 * np.pi * 2700 * t)).astype(np.float32)
    buf = io.BytesIO()
    sf.write(buf, audio, sr, format="WAV", subtype="PCM_16")
    return buf.getvalue()


def _encode_multipart(
    parts: list[tuple[str, str, bytes]],
    boundary: str = "----TestBoundary123",
) -> tuple[bytes, str]:
    chunks: list[bytes] = []
    for field_name, filename, data in parts:
        header = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{field_name}"; '
            f'filename="{filename}"\r\n'
            f"Content-Type: application/octet-stream\r\n"
            f"\r\n"
        ).encode("utf-8")
        chunks.append(header + data + b"\r\n")
    body = b"".join(chunks) + f"--{boundary}--\r\n".encode("utf-8")
    return body, f"multipart/form-data; boundary={boundary}"


@pytest.fixture
def api_http(tmp_path: Path):
    output_dir = tmp_path / "output"
    upload_dir = tmp_path / "uploads"
    field_dir = tmp_path / "field"
    field_dir.mkdir()
    httpd = ThreadingHTTPServer(
        ("127.0.0.1", 0),
        api.make_handler(output_dir, upload_dir, field_dir=field_dir),
    )
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield {
            "port": httpd.server_address[1],
            "output_dir": output_dir,
            "upload_dir": upload_dir,
            "field_dir": field_dir,
        }
    finally:
        httpd.shutdown()
        httpd.server_close()


def _request(
    port: int,
    method: str,
    path: str,
    body: bytes | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 120.0,
) -> tuple[int, bytes, dict[str, str]]:
    conn = HTTPConnection("127.0.0.1", port, timeout=timeout)
    conn.request(method, path, body=body, headers=headers or {})
    resp = conn.getresponse()
    raw = resp.read()
    hdrs = {k.lower(): v for k, v in resp.getheaders()}
    conn.close()
    return resp.status, raw, hdrs


def test_health_and_limits(api_http):
    port = api_http["port"]
    status, raw, _ = _request(port, "GET", "/api/health")
    assert status == 200
    assert json.loads(raw)["ok"] is True

    status, raw, _ = _request(port, "GET", "/api/limits")
    assert status == 200
    payload = json.loads(raw)
    assert payload == {
        "max_files": 10,
        "max_bytes": 2 * 1024 * 1024 * 1024,
        "extensions": [".wav", ".flac", ".ogg", ".mp3", ".m4a"],
    }


def test_options_allows_post(api_http):
    port = api_http["port"]
    status, _, headers = _request(port, "OPTIONS", "/api/analyze")
    assert status == 204
    assert headers["access-control-allow-origin"] == "*"
    methods = {m.strip() for m in headers["access-control-allow-methods"].split(",")}
    assert methods >= {"GET", "POST", "OPTIONS"}
    assert "content-type" in headers["access-control-allow-headers"].lower()


def test_reject_bad_extension(api_http):
    port = api_http["port"]
    body, ctype = _encode_multipart([("files", "notes.txt", b"hello")])
    status, raw, _ = _request(
        port, "POST", "/api/analyze", body=body, headers={"Content-Type": ctype}
    )
    assert status == 400
    err = json.loads(raw)
    assert "error" in err
    assert ".txt" in err["error"]


def test_reject_empty_file(api_http):
    port = api_http["port"]
    body, ctype = _encode_multipart([("files", "empty.wav", b"")])
    status, raw, _ = _request(
        port, "POST", "/api/analyze", body=body, headers={"Content-Type": ctype}
    )
    assert status == 400
    assert "empty" in json.loads(raw)["error"].lower()


def test_reject_oversize_file(api_http, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(api, "MAX_BYTES_PER_FILE", 64)
    port = api_http["port"]
    body, ctype = _encode_multipart([("files", "huge.wav", b"x" * 200)])
    status, raw, _ = _request(
        port, "POST", "/api/analyze", body=body, headers={"Content-Type": ctype}
    )
    assert status == 413
    err = json.loads(raw)["error"].lower()
    assert "too large" in err
    assert "413" in err or "64" in err


def test_reject_oversize_content_length(api_http, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(api, "MAX_FILES_PER_REQUEST", 1)
    monkeypatch.setattr(api, "MAX_BYTES_PER_FILE", 100)
    port = api_http["port"]
    conn = HTTPConnection("127.0.0.1", port, timeout=5)
    conn.putrequest("POST", "/api/analyze")
    conn.putheader("Content-Type", "multipart/form-data; boundary=abc")
    conn.putheader("Content-Length", str(2_000_000))
    conn.endheaders()
    resp = conn.getresponse()
    raw = resp.read()
    conn.close()
    assert resp.status == 413
    assert "too large" in json.loads(raw)["error"].lower()


def test_reject_too_many_files(api_http, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(api, "MAX_FILES_PER_REQUEST", 2)
    port = api_http["port"]
    wav = _wav_bytes(duration_s=0.2)
    parts = [("files", f"clip{i}.wav", wav) for i in range(3)]
    body, ctype = _encode_multipart(parts)
    status, raw, _ = _request(
        port, "POST", "/api/analyze", body=body, headers={"Content-Type": ctype}
    )
    assert status == 400
    assert "too many" in json.loads(raw)["error"].lower()


def test_analyze_tiny_wav_returns_report(api_http):
    port = api_http["port"]
    wav = _wav_bytes()
    body, ctype = _encode_multipart([("files", "R20241011-180923.WAV", wav)])
    status, raw, headers = _request(
        port, "POST", "/api/analyze", body=body, headers={"Content-Type": ctype}
    )
    assert status == 200, raw
    assert headers["access-control-allow-origin"] == "*"
    payload = json.loads(raw)
    assert "files" in payload and "events" in payload and "summary" in payload
    assert payload["summary"]["n_files"] == 1
    assert payload["files"][0]["file"] == "R20241011-180923.WAV"
    assert payload["files"][0]["recorded_at"] == "2024-10-11T18:09:23"
    assert isinstance(payload["events"], list)
    assert (api_http["output_dir"] / "resultado.json").exists()
    assert (api_http["output_dir"] / "resultado.xlsx").exists()

    status, report_raw, _ = _request(port, "GET", "/api/report")
    assert status == 200
    assert json.loads(report_raw)["summary"]["n_files"] == 1


def test_analyze_accepts_file_field_and_unparsed_name(api_http):
    port = api_http["port"]
    wav = _wav_bytes()
    body, ctype = _encode_multipart([("file", "frog.wav", wav)])
    status, raw, _ = _request(
        port, "POST", "/api/analyze", body=body, headers={"Content-Type": ctype}
    )
    assert status == 200, raw
    payload = json.loads(raw)
    assert payload["files"][0]["file"] == "frog.wav"
    assert payload["files"][0]["recorded_at"] is None
    assert payload["summary"]["n_files"] == 1
    cfg = DetectionConfig()
    assert payload["config"]["sample_rate"] == cfg.sample_rate


def test_parse_event_spectrogram_request_rejects_bad_input():
    with pytest.raises(api.AnalyzeError):
        api.parse_event_spectrogram_request({})
    with pytest.raises(api.AnalyzeError, match="basename"):
        api.parse_event_spectrogram_request(
            {
                "file": ["../secret.wav"],
                "start_s": ["1"],
                "end_s": ["2"],
                "peak_time_s": ["1.5"],
                "peak_freq_hz": ["2700"],
            }
        )
    with pytest.raises(api.AnalyzeError, match="end_s"):
        api.parse_event_spectrogram_request(
            {
                "file": ["clip.wav"],
                "start_s": ["2"],
                "end_s": ["1"],
                "peak_time_s": ["1.5"],
                "peak_freq_hz": ["2700"],
            }
        )


def test_event_spectrogram_missing_audio(api_http):
    port = api_http["port"]
    qs = urlencode(
        {
            "file": "missing.wav",
            "start_s": "2.276",
            "end_s": "2.368",
            "peak_time_s": "2.299",
            "peak_freq_hz": "2713.2",
        }
    )
    status, raw, headers = _request(port, "GET", f"/api/event-spectrogram?{qs}")
    assert status == 404
    payload = json.loads(raw)
    assert payload["code"] == "audio_not_found"
    assert "não está nesta máquina" in payload["error"]
    assert headers["content-type"].startswith("application/json")


def test_event_spectrogram_rejects_missing_params(api_http):
    port = api_http["port"]
    status, raw, _ = _request(port, "GET", "/api/event-spectrogram?file=clip.wav")
    assert status == 400
    assert "missing" in json.loads(raw)["error"]


def test_event_spectrogram_png_for_known_peak(api_http):
    """On-demand PNG for a short in-band tone; marks the table row, does not re-detect."""
    from io import BytesIO

    from PIL import Image

    field_dir: Path = api_http["field_dir"]
    campaign = field_dir / "10_10_25 açude 1"
    campaign.mkdir()
    wav_path = campaign / "R20241011-180923.WAV"
    sr = 22_050
    duration_s = 6.0
    n = int(sr * duration_s)
    t = np.arange(n) / sr
    audio = (0.01 * np.random.default_rng(3).standard_normal(n)).astype(np.float32)
    tone = (t >= 2.20) & (t < 2.40)
    audio[tone] += (0.45 * np.sin(2 * np.pi * 2713.0 * t[tone])).astype(np.float32)
    sf.write(str(wav_path), audio, sr, subtype="PCM_16")

    qs = urlencode(
        {
            "file": "R20241011-180923.WAV",
            "start_s": "2.276",
            "end_s": "2.368",
            "peak_time_s": "2.299",
            "peak_freq_hz": "2713.2",
            "n_callers": "1",
            "event": "1",
        }
    )
    status, raw, headers = _request(
        api_http["port"], "GET", f"/api/event-spectrogram?{qs}", timeout=60.0
    )
    assert status == 200, raw[:500]
    assert headers["content-type"] == "image/png"
    assert len(raw) > 2000
    image = Image.open(BytesIO(raw))
    assert image.format == "PNG"
    assert image.size[0] > 100 and image.size[1] > 80
    assert headers["x-peak-time-s"].startswith("2.299")
    assert float(headers["x-peak-freq-hz"]) == pytest.approx(2713.2, abs=0.05)
    window_start = float(headers["x-window-start-s"])
    window_dur = float(headers["x-window-duration-s"])
    assert window_start == pytest.approx(2.276 - 1.25, abs=0.05)
    assert window_dur > 2.0
    assert headers["x-event-file"] == "R20241011-180923.WAV"
    cached = list((api_http["output_dir"] / "event_spectrograms").glob("*.png"))
    assert cached and cached[0].stat().st_size > 2000

    # Second request hits the cache (same PNG).
    status2, raw2, _ = _request(
        api_http["port"], "GET", f"/api/event-spectrogram?{qs}", timeout=30.0
    )
    assert status2 == 200
    assert raw2 == raw


def test_file_spectrogram_on_demand_when_png_missing(api_http):
    """GET /api/spectrograms/{stem}_spectrogram.png generates and caches when audio + JSON exist."""
    from io import BytesIO

    from PIL import Image

    output_dir: Path = api_http["output_dir"]
    field_dir: Path = api_http["field_dir"]
    campaign = field_dir / "10_10_25 açude 1"
    campaign.mkdir()
    wav_name = "R20241011-180923.WAV"
    wav_path = campaign / wav_name
    sr = 22_050
    duration_s = 8.0
    n = int(sr * duration_s)
    t = np.arange(n) / sr
    audio = (0.01 * np.random.default_rng(7).standard_normal(n)).astype(np.float32)
    tone = (t >= 5.0) & (t < 5.4)
    audio[tone] += (0.45 * np.sin(2 * np.pi * 2713.0 * t[tone])).astype(np.float32)
    sf.write(str(wav_path), audio, sr, subtype="PCM_16")

    report = {
        "generated_at": "2026-01-01T00:00:00+00:00",
        "species": "Sphaenorhynchus caramaschii",
        "common_name": "perereca-de-banhado",
        "config": {"sample_rate": sr, "lowcut_hz": 2600.0, "highcut_hz": 3200.0, "threshold_k": 6.0},
        "summary": {"n_files": 1, "n_events": 1, "max_simultaneous": 1, "total_duration_s": duration_s},
        "files": [
            {
                "file": wav_name,
                "recorded_at": "2024-10-11T18:09:23",
                "duration_s": duration_s,
                "n_events": 1,
                "max_simultaneous": 1,
                "threshold": 20.0,
                "spectrogram": "",
            }
        ],
        "events": [
            {
                "file": wav_name,
                "recorded_at": "2024-10-11T18:09:23",
                "event": 1,
                "start_s": 5.05,
                "end_s": 5.35,
                "peak_time_s": 5.2,
                "peak_freq_hz": 2713.0,
                "energy": 1.0,
                "n_callers": 1,
                "duration_s": 0.3,
            }
        ],
        "by_hour": [{"hour": h, "n_events": 0} for h in range(24)],
        "by_month": [{"month": m, "n_events": 0} for m in range(1, 13)],
    }
    (output_dir / "resultado.json").write_text(json.dumps(report), encoding="utf-8")
    png_name = "R20241011-180923_spectrogram.png"
    cache_path = output_dir / png_name
    assert not cache_path.exists()

    port = api_http["port"]
    status, raw, headers = _request(
        port, "GET", f"/api/spectrograms/{png_name}", timeout=60.0
    )
    assert status == 200, raw[:500]
    assert headers["content-type"] == "image/png"
    assert len(raw) > 2000
    image = Image.open(BytesIO(raw))
    assert image.format == "PNG"
    assert cache_path.is_file() and cache_path.stat().st_size > 2000

    status2, raw2, _ = _request(port, "GET", f"/api/spectrograms/{png_name}", timeout=30.0)
    assert status2 == 200
    assert raw2 == raw


def test_file_spectrogram_missing_audio(api_http):
    output_dir: Path = api_http["output_dir"]
    wav_name = "R20241011-180923.WAV"
    report = {
        "generated_at": "2026-01-01T00:00:00+00:00",
        "species": "Sphaenorhynchus caramaschii",
        "common_name": "perereca-de-banhado",
        "config": {"sample_rate": 22050, "lowcut_hz": 2600.0, "highcut_hz": 3200.0, "threshold_k": 6.0},
        "summary": {"n_files": 1, "n_events": 0, "max_simultaneous": 0, "total_duration_s": 60.0},
        "files": [
            {
                "file": wav_name,
                "recorded_at": "2024-10-11T18:09:23",
                "duration_s": 60.0,
                "n_events": 0,
                "max_simultaneous": 0,
                "threshold": 20.0,
                "spectrogram": "",
            }
        ],
        "events": [],
        "by_hour": [{"hour": h, "n_events": 0} for h in range(24)],
        "by_month": [{"month": m, "n_events": 0} for m in range(1, 13)],
    }
    (output_dir / "resultado.json").write_text(json.dumps(report), encoding="utf-8")
    png_name = "R20241011-180923_spectrogram.png"
    status, raw, _ = _request(api_http["port"], "GET", f"/api/spectrograms/{png_name}")
    assert status == 404
    payload = json.loads(raw)
    assert payload["code"] == "audio_not_found"
    assert "não está nesta máquina" in payload["error"]
