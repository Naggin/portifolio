"""HTTP API: upload limits, analyze, and existing report endpoints."""

from __future__ import annotations

import io
import json
import sys
import threading
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bioacoustics import api  # noqa: E402
from bioacoustics.config import DetectionConfig  # noqa: E402
from generate_sample import synthesize  # noqa: E402


def _wav_bytes(duration_s: float = 2.0, sr: int = 22_050, seed: int | None = None) -> bytes:
    if seed is None:
        audio = np.zeros(int(sr * duration_s), dtype=np.float32)
    else:
        audio = synthesize(sr=sr, duration_s=duration_s, seed=seed)
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
    httpd = ThreadingHTTPServer(
        ("127.0.0.1", 0),
        api.make_handler(output_dir, upload_dir),
    )
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield {
            "port": httpd.server_address[1],
            "output_dir": output_dir,
            "upload_dir": upload_dir,
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
        "max_bytes": 500 * 1024 * 1024,
        "extensions": [".wav", ".flac", ".ogg", ".mp3"],
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
    wav = _wav_bytes(duration_s=5.0, seed=42)
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
    wav = _wav_bytes(duration_s=2.0)
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
