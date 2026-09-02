"""Tiny HTTP API so the React dashboard can read pipeline output and upload audio.

Serves the JSON report and spectrogram PNGs from ``output/``. Run with:

    PYTHONPATH=src python -m bioacoustics.api
"""

from __future__ import annotations

import argparse
import json
import tempfile
import threading
import traceback
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import BinaryIO
from urllib.parse import unquote, urlparse

from .config import AUDIO_EXTENSIONS, DetectionConfig
from .pipeline import process_file
from .report import write_json_report, write_report
from .visualization import save_file_spectrograms

DEFAULT_OUTPUT = Path("output")
DEFAULT_UPLOAD_DIR = Path("data/uploads")
JSON_NAME = "resultado.json"
XLSX_NAME = "resultado.xlsx"

# Same extensions as ``DetectionConfig`` / the CLI. Easy to change.
ALLOWED_EXTENSIONS = AUDIO_EXTENSIONS
MAX_FILES_PER_REQUEST = 10
MAX_BYTES_PER_FILE = 2 * 1024 * 1024 * 1024  # 2 GB — 1 h WAV / 6 h MP3 field files
# Multipart headers / boundaries on top of the file payloads.
MULTIPART_OVERHEAD_BYTES = 1 * 1024 * 1024  # 1 MB

FILE_FIELD_NAMES = frozenset({"files", "file"})
_MAX_HEADER_BYTES = 64 * 1024

_ANALYZE_LOCK = threading.Lock()


class AnalyzeError(Exception):
    """Client-facing analysis error with an HTTP status code."""

    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


def max_request_bytes() -> int:
    """Reject a body larger than this before reading it."""
    return MAX_FILES_PER_REQUEST * MAX_BYTES_PER_FILE + MULTIPART_OVERHEAD_BYTES


def limits_payload() -> dict[str, object]:
    return {
        "max_files": MAX_FILES_PER_REQUEST,
        "max_bytes": MAX_BYTES_PER_FILE,
        "extensions": list(ALLOWED_EXTENSIONS),
    }


def _json_bytes(payload: object, status: int = 200) -> tuple[int, bytes, str]:
    return status, json.dumps(payload).encode("utf-8"), "application/json; charset=utf-8"


def _safe_filename(name: str) -> str:
    base = Path(str(name).replace("\\", "/")).name
    if not base or base in {".", ".."}:
        return "upload"
    return base


def _unique_path(directory: Path, filename: str) -> Path:
    dest = directory / _safe_filename(filename)
    if not dest.exists():
        return dest
    stem, suffix = dest.stem, dest.suffix
    n = 2
    while True:
        candidate = directory / f"{stem}_{n}{suffix}"
        if not candidate.exists():
            return candidate
        n += 1


def _parse_boundary(content_type: str | None) -> str:
    if not content_type:
        raise AnalyzeError("expected multipart/form-data")
    parts = [p.strip() for p in content_type.split(";")]
    ctype = parts[0].lower()
    if ctype != "multipart/form-data":
        raise AnalyzeError("expected multipart/form-data")
    for param in parts[1:]:
        if "=" not in param:
            continue
        key, value = param.split("=", 1)
        if key.strip().lower() != "boundary":
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] == '"':
            value = value[1:-1]
        if not value:
            break
        return value
    raise AnalyzeError("multipart boundary missing")


def _parse_content_length(headers) -> int:
    raw = headers.get("Content-Length")
    if raw is None or str(raw).strip() == "":
        raise AnalyzeError("Content-Length required")
    try:
        length = int(raw)
    except (TypeError, ValueError) as exc:
        raise AnalyzeError("invalid Content-Length") from exc
    if length < 0:
        raise AnalyzeError("invalid Content-Length")
    if length > max_request_bytes():
        raise AnalyzeError(
            f"request too large (max {MAX_FILES_PER_REQUEST} files × "
            f"{MAX_BYTES_PER_FILE} bytes; HTTP 413)",
            413,
        )
    return length


def _parse_content_disposition(value: str) -> tuple[str | None, str | None]:
    """Return ``(name, filename)`` from a Content-Disposition header."""
    name: str | None = None
    filename: str | None = None
    pieces: list[str] = []
    buf: list[str] = []
    in_quotes = False
    for ch in value:
        if ch == '"':
            in_quotes = not in_quotes
        if ch == ";" and not in_quotes:
            pieces.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
    if buf:
        pieces.append("".join(buf).strip())

    for piece in pieces[1:]:
        if "=" not in piece:
            continue
        key, raw = piece.split("=", 1)
        key = key.strip().lower()
        raw = raw.strip()
        if len(raw) >= 2 and raw[0] == raw[-1] == '"':
            raw = raw[1:-1]
        if key == "name":
            name = raw
        elif key == "filename*":
            encoded = raw.split("''", 1)[-1]
            filename = unquote(encoded)
        elif key == "filename" and filename is None:
            filename = raw
    return name, filename


class _BoundedReader:
    """Read at most ``remaining`` bytes from ``rfile``, with pushback."""

    def __init__(self, rfile, remaining: int) -> None:
        self._rfile = rfile
        self._remaining = remaining
        self._push = bytearray()

    def unread(self, data: bytes) -> None:
        if data:
            self._push[0:0] = data

    def read(self, size: int) -> bytes:
        if size <= 0:
            return b""
        out = bytearray()
        if self._push:
            take = min(size, len(self._push))
            out += self._push[:take]
            del self._push[:take]
            size -= take
        if size > 0 and self._remaining > 0:
            n = min(size, self._remaining)
            got = bytearray()
            while len(got) < n:
                chunk = self._rfile.read(n - len(got))
                if not chunk:
                    break
                got += chunk
            self._remaining -= len(got)
            out += got
        return bytes(out)

    def drain(self) -> None:
        try:
            while self.read(65_536):
                pass
        except OSError:
            pass


def _stream_until(
    stream: _BoundedReader,
    needle: bytes,
    dest: BinaryIO | None,
    max_bytes: int,
    limit_message: str,
    status: int = 413,
) -> int:
    """Write bytes to ``dest`` until ``needle``. Needle is consumed, not written."""
    written = 0
    buf = b""
    overlap = max(len(needle) - 1, 0)
    chunk_size = 64 * 1024
    while True:
        chunk = stream.read(chunk_size)
        if not chunk:
            raise AnalyzeError("malformed multipart body")
        buf += chunk
        idx = buf.find(needle)
        if idx != -1:
            piece = buf[:idx]
            written += len(piece)
            if written > max_bytes:
                raise AnalyzeError(limit_message, status)
            if dest is not None:
                dest.write(piece)
            stream.unread(buf[idx + len(needle) :])
            return written
        if len(buf) > overlap:
            flush, buf = buf[:-overlap], buf[-overlap:]
            written += len(flush)
            if written > max_bytes:
                raise AnalyzeError(limit_message, status)
            if dest is not None:
                dest.write(flush)


@dataclass
class SavedUpload:
    filename: str
    path: Path
    size: int


def save_multipart_uploads(stream: _BoundedReader, boundary: str, dest_dir: Path) -> list[SavedUpload]:
    """Parse multipart/form-data and write ``files`` / ``file`` parts to disk."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    boundary_b = boundary.encode("utf-8")
    first = b"--" + boundary_b
    sep = b"\r\n--" + boundary_b
    _stream_until(
        stream,
        first,
        None,
        _MAX_HEADER_BYTES,
        "malformed multipart body",
        400,
    )

    saved: list[SavedUpload] = []
    while True:
        marker = stream.read(2)
        if marker == b"--":
            break
        if marker != b"\r\n":
            raise AnalyzeError("malformed multipart body")

        header_buf = tempfile.SpooledTemporaryFile(max_size=_MAX_HEADER_BYTES)
        try:
            _stream_until(
                stream,
                b"\r\n\r\n",
                header_buf,
                _MAX_HEADER_BYTES,
                "multipart headers too large",
                400,
            )
            header_buf.seek(0)
            headers = _parse_part_headers(header_buf.read())
        finally:
            header_buf.close()

        name, filename = _parse_content_disposition(headers.get("content-disposition", ""))
        is_file = name in FILE_FIELD_NAMES and bool(filename)
        if is_file:
            if len(saved) >= MAX_FILES_PER_REQUEST:
                raise AnalyzeError(f"too many files (max {MAX_FILES_PER_REQUEST})")
            ext = Path(_safe_filename(filename)).suffix.lower()
            if ext not in ALLOWED_EXTENSIONS:
                allowed = ", ".join(ALLOWED_EXTENSIONS)
                raise AnalyzeError(f"unsupported file type: {ext or '(none)'} (allowed: {allowed})")
            out_path = _unique_path(dest_dir, filename)
            with out_path.open("wb") as fh:
                size = _stream_until(
                    stream,
                    sep,
                    fh,
                    MAX_BYTES_PER_FILE,
                    f"file too large (max {MAX_BYTES_PER_FILE} bytes / "
                    f"{MAX_BYTES_PER_FILE // (1024 * 1024)} MB; HTTP 413)",
                    413,
                )
            if size <= 0:
                out_path.unlink(missing_ok=True)
                raise AnalyzeError(f"empty file: {_safe_filename(filename)}")
            saved.append(SavedUpload(filename=_safe_filename(filename), path=out_path, size=size))
        else:
            _stream_until(
                stream,
                sep,
                None,
                max_request_bytes(),
                "request too large (HTTP 413)",
                413,
            )
    return saved


def _parse_part_headers(raw: bytes) -> dict[str, str]:
    headers: dict[str, str] = {}
    text = raw.decode("latin-1")
    for line in text.split("\r\n"):
        if not line or ":" not in line:
            continue
        key, value = line.split(":", 1)
        headers[key.strip().lower()] = value.strip()
    return headers


def run_pipeline_on_uploads(uploads: list[SavedUpload], output_dir: Path) -> dict:
    """Process saved uploads and write resultado.json / resultado.xlsx."""
    if not uploads:
        raise AnalyzeError("no audio files in request")
    cfg = DetectionConfig()
    output_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for upload in uploads:
        result = process_file(upload.path, cfg)
        save_file_spectrograms(
            upload.path,
            result.detection.events,
            result.detection.duration_s,
            cfg,
            output_dir,
            result=result.detection,
        )
        results.append(result)
    json_path = write_json_report(results, output_dir / JSON_NAME, cfg)
    write_report(results, output_dir / XLSX_NAME)
    return json.loads(json_path.read_text(encoding="utf-8"))


def make_handler(output_dir: Path, upload_dir: Path | None = None):
    output_dir = output_dir.resolve()
    upload_dir = (upload_dir or DEFAULT_UPLOAD_DIR).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    upload_dir.mkdir(parents=True, exist_ok=True)

    class DashboardHandler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args) -> None:  # noqa: A003
            print(f"[api] {self.address_string()} {format % args}")

        def _send(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_OPTIONS(self) -> None:  # noqa: N802
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()

        def do_GET(self) -> None:  # noqa: N802
            path = unquote(urlparse(self.path).path)
            if path in {"/api/report", "/api/report/"}:
                report = output_dir / JSON_NAME
                if not report.exists():
                    self._send(*_json_bytes(
                        {"error": "resultado.json not found. Run the detection pipeline first."},
                        404,
                    ))
                    return
                self._send(200, report.read_bytes(), "application/json; charset=utf-8")
                return

            if path.startswith("/api/spectrograms/"):
                name = Path(path.removeprefix("/api/spectrograms/")).name
                if not name.endswith(".png"):
                    self._send(*_json_bytes({"error": "spectrogram must be a .png"}, 400))
                    return
                png = (output_dir / name).resolve()
                if not str(png).startswith(str(output_dir)) or not png.exists():
                    self._send(*_json_bytes({"error": "spectrogram not found"}, 404))
                    return
                self._send(200, png.read_bytes(), "image/png")
                return

            if path in {"/api/health", "/api/health/"}:
                self._send(*_json_bytes({"ok": True, "output": str(output_dir)}))
                return

            if path in {"/api/limits", "/api/limits/"}:
                self._send(*_json_bytes(limits_payload()))
                return

            self._send(*_json_bytes({"error": "not found"}, 404))

        def do_POST(self) -> None:  # noqa: N802
            path = unquote(urlparse(self.path).path)
            if path not in {"/api/analyze", "/api/analyze/"}:
                self._send(*_json_bytes({"error": "not found"}, 404))
                return
            self._handle_analyze()

        def _handle_analyze(self) -> None:
            stream: _BoundedReader | None = None
            try:
                length = _parse_content_length(self.headers)
            except AnalyzeError as exc:
                self.close_connection = True
                self._send(*_json_bytes({"error": str(exc)}, exc.status))
                return

            try:
                boundary = _parse_boundary(self.headers.get("Content-Type"))
            except AnalyzeError as exc:
                self.close_connection = True
                self._send(*_json_bytes({"error": str(exc)}, exc.status))
                return

            with _ANALYZE_LOCK:
                request_dir = Path(tempfile.mkdtemp(prefix="analyze_", dir=str(upload_dir)))
                try:
                    stream = _BoundedReader(self.rfile, length)
                    uploads = save_multipart_uploads(stream, boundary, request_dir)
                    stream.drain()
                    payload = run_pipeline_on_uploads(uploads, output_dir)
                    self._send(*_json_bytes(payload))
                except AnalyzeError as exc:
                    if stream is not None:
                        stream.drain()
                    self.close_connection = True
                    self._send(*_json_bytes({"error": str(exc)}, exc.status))
                except Exception as exc:
                    traceback.print_exc()
                    if stream is not None:
                        stream.drain()
                    self.close_connection = True
                    self._send(*_json_bytes({"error": f"analysis failed: {exc}"}, 500))

    return DashboardHandler


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve detection reports for the dashboard.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--upload-dir", default=str(DEFAULT_UPLOAD_DIR))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    upload_dir = Path(args.upload_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    upload_dir.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer((args.host, args.port), make_handler(output_dir, upload_dir))
    print(f"Dashboard API at http://{args.host}:{args.port}/api/report")
    print(f"Upload/analyze at http://{args.host}:{args.port}/api/analyze")
    print(f"Reading outputs from {output_dir}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping.")
        server.server_close()


if __name__ == "__main__":
    main()
