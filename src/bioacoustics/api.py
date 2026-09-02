"""Tiny HTTP API so the React dashboard can read pipeline output and upload audio.

Serves the JSON report and spectrogram PNGs from ``output/``. File-level and
per-event spectrograms are generated on demand from local field/upload audio
(``GET /api/spectrograms/{name}.png``, ``GET /api/event-spectrogram``). Run with:

    PYTHONPATH=src python -m bioacoustics.api
"""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
import threading
import traceback
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import BinaryIO, Sequence
from urllib.parse import parse_qs, unquote, urlparse

from .audio_io import audio_duration_s
from .config import AUDIO_EXTENSIONS, DetectionConfig
from .pipeline import process_file
from .report import write_json_report, write_report
from .visualization import (
    EVENT_CONTEXT_PAD_S,
    event_context_window,
    save_event_spectrogram,
    save_file_spectrograms,
)

DEFAULT_OUTPUT = Path("output")
DEFAULT_UPLOAD_DIR = Path("data/uploads")
DEFAULT_FIELD_DIR = Path("data/field")
JSON_NAME = "resultado.json"
XLSX_NAME = "resultado.xlsx"
EVENT_SPEC_DIR = "event_spectrograms"
AUDIO_MISSING_MESSAGE = "áudio deste ficheiro não está nesta máquina"
MAX_EVENT_TIME_S = 48 * 3600.0
_SPEC_LOCK = threading.Lock()

# Same extensions as ``DetectionConfig`` / the CLI. Easy to change.
ALLOWED_EXTENSIONS = AUDIO_EXTENSIONS
MAX_FILES_PER_REQUEST = 10
MAX_BYTES_PER_FILE = 2 * 1024 * 1024 * 1024  # 2 GB — 1 h WAV / 6 h MP3 field files
# Multipart headers / boundaries on top of the file payloads.
MULTIPART_OVERHEAD_BYTES = 1 * 1024 * 1024  # 1 MB

FILE_FIELD_NAMES = frozenset({"files", "file"})
_MAX_HEADER_BYTES = 64 * 1024

_ANALYZE_LOCK = threading.Lock()


@dataclass(frozen=True)
class EventSpectrogramRequest:
    filename: str
    start_s: float
    end_s: float
    peak_time_s: float
    peak_freq_hz: float
    n_callers: int | None = None
    event: int | None = None


def _safe_audio_basename(name: str) -> str:
    """Basename only; reject path fragments."""
    raw = str(name).strip()
    if not raw or raw in {".", ".."}:
        raise AnalyzeError("file is required")
    if "/" in raw.replace("\\", "/") or ".." in Path(raw).parts:
        raise AnalyzeError("file must be a basename, not a path")
    base = Path(raw.replace("\\", "/")).name
    if not base or base in {".", ".."}:
        raise AnalyzeError("file is required")
    ext = Path(base).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        allowed = ", ".join(ALLOWED_EXTENSIONS)
        raise AnalyzeError(f"unsupported file type: {ext or '(none)'} (allowed: {allowed})")
    return base


def _query_one(query: dict[str, list[str]], key: str) -> str | None:
    values = query.get(key) or query.get(key + "[]")
    if not values:
        return None
    value = values[0].strip()
    return value if value else None


def _query_float(query: dict[str, list[str]], key: str, *, required: bool = True) -> float | None:
    raw = _query_one(query, key)
    if raw is None:
        if required:
            raise AnalyzeError(f"missing parameter: {key}")
        return None
    try:
        value = float(raw)
    except ValueError as exc:
        raise AnalyzeError(f"invalid {key}") from exc
    if value != value or value in (float("inf"), float("-inf")):  # NaN / Inf
        raise AnalyzeError(f"invalid {key}")
    return value


def _query_int(query: dict[str, list[str]], key: str) -> int | None:
    raw = _query_one(query, key)
    if raw is None:
        return None
    try:
        value = int(raw, 10)
    except ValueError as exc:
        raise AnalyzeError(f"invalid {key}") from exc
    if value < 1:
        raise AnalyzeError(f"invalid {key}")
    return value


def parse_event_spectrogram_request(query: dict[str, list[str]]) -> EventSpectrogramRequest:
    """Validate GET /api/event-spectrogram query params (table-row values)."""
    filename_raw = _query_one(query, "file")
    if not filename_raw:
        raise AnalyzeError("missing parameter: file")
    filename = _safe_audio_basename(filename_raw)
    start_s = _query_float(query, "start_s")
    end_s = _query_float(query, "end_s")
    peak_time_s = _query_float(query, "peak_time_s")
    peak_freq_hz = _query_float(query, "peak_freq_hz")
    assert start_s is not None and end_s is not None
    assert peak_time_s is not None and peak_freq_hz is not None
    if start_s < 0 or end_s < 0 or peak_time_s < 0:
        raise AnalyzeError("times must be >= 0")
    if end_s < start_s:
        raise AnalyzeError("end_s must be >= start_s")
    if max(start_s, end_s, peak_time_s) > MAX_EVENT_TIME_S:
        raise AnalyzeError("time out of range")
    if not (1.0 <= peak_freq_hz <= 20_000.0):
        raise AnalyzeError("peak_freq_hz out of range")
    return EventSpectrogramRequest(
        filename=filename,
        start_s=start_s,
        end_s=end_s,
        peak_time_s=peak_time_s,
        peak_freq_hz=peak_freq_hz,
        n_callers=_query_int(query, "n_callers"),
        event=_query_int(query, "event"),
    )


def find_audio_by_basename(filename: str, roots: Sequence[Path]) -> Path | None:
    """Locate ``filename`` under field / output / uploads (rglob, case-insensitive)."""
    wanted = filename.lower()
    for root in roots:
        root = Path(root)
        if not root.exists():
            continue
        direct = root / filename
        if direct.is_file():
            return direct
        try:
            for path in root.rglob("*"):
                if EVENT_SPEC_DIR in path.parts:
                    continue
                if path.is_file() and path.name.lower() == wanted:
                    return path
        except OSError:
            continue
    return None


def file_spectrogram_stem(png_name: str) -> str:
    """``R20241011-180923_spectrogram.png`` → ``R20241011-180923``."""
    base = Path(png_name).name
    if base.endswith("_spectrogram.png"):
        return base[: -len("_spectrogram.png")]
    return Path(base).stem


def find_audio_for_spectrogram_stem(stem: str, roots: Sequence[Path]) -> Path | None:
    """Resolve field/upload audio from a PNG stem or report basename."""
    stem = stem.strip()
    if not stem:
        return None
    for ext in ALLOWED_EXTENSIONS:
        found = find_audio_by_basename(f"{stem}{ext}", roots)
        if found is not None:
            return found
    wanted = stem.lower()
    for root in roots:
        root = Path(root)
        if not root.exists():
            continue
        try:
            for path in root.rglob("*"):
                if EVENT_SPEC_DIR in path.parts:
                    continue
                if path.is_file() and path.stem.lower() == wanted:
                    return path
        except OSError:
            continue
    return None


def load_report_events_for_file(output_dir: Path, audio_filename: str) -> tuple[list[dict], float] | None:
    """Events and duration for ``audio_filename`` from ``resultado.json``."""
    report_path = output_dir / JSON_NAME
    if not report_path.is_file():
        return None
    try:
        payload = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    duration_s: float | None = None
    for row in payload.get("files") or []:
        if isinstance(row, dict) and row.get("file") == audio_filename:
            try:
                duration_s = float(row.get("duration_s", 0.0))
            except (TypeError, ValueError):
                duration_s = 0.0
            break
    if duration_s is None:
        return None
    events = [
        ev
        for ev in payload.get("events") or []
        if isinstance(ev, dict) and ev.get("file") == audio_filename
    ]
    return events, duration_s


def render_file_spectrogram(
    png_name: str,
    output_dir: Path,
    audio_roots: Sequence[Path],
    cfg: DetectionConfig | None = None,
) -> Path:
    """Write (or reuse) ``output/{stem}_spectrogram.png`` for the densest peak window."""
    cache_path = (Path(output_dir) / Path(png_name).name).resolve()
    output_resolved = Path(output_dir).resolve()
    if not str(cache_path).startswith(str(output_resolved)):
        raise AnalyzeError("invalid spectrogram path", 400)

    if cache_path.is_file() and cache_path.stat().st_size > 0:
        return cache_path

    stem = file_spectrogram_stem(png_name)
    audio_path = find_audio_for_spectrogram_stem(stem, audio_roots)
    if audio_path is None:
        raise AnalyzeError(AUDIO_MISSING_MESSAGE, 404)

    loaded = load_report_events_for_file(output_dir, audio_path.name)
    if loaded is None:
        raise AnalyzeError("resultado.json not found or file missing from report", 404)
    events, duration_s = loaded
    if duration_s <= 0:
        duration_s = audio_duration_s(audio_path)

    cfg = cfg or DetectionConfig()
    with _SPEC_LOCK:
        if cache_path.is_file() and cache_path.stat().st_size > 0:
            return cache_path
        save_file_spectrograms(
            audio_path,
            events,
            duration_s,
            cfg,
            output_dir,
            write_zoom=False,
        )
    if not cache_path.is_file() or cache_path.stat().st_size <= 0:
        raise AnalyzeError("spectrogram generation failed", 500)
    return cache_path


def event_spectrogram_cache_path(output_dir: Path, req: EventSpectrogramRequest) -> Path:
    key = (
        f"{req.filename}|{req.start_s:.6f}|{req.end_s:.6f}|"
        f"{req.peak_time_s:.6f}|{req.peak_freq_hz:.3f}|"
        f"{req.n_callers}|{req.event}|{EVENT_CONTEXT_PAD_S}"
    )
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:20]
    stem = Path(req.filename).stem[:40]
    return Path(output_dir) / EVENT_SPEC_DIR / f"{stem}_{digest}.png"


def render_event_spectrogram(
    req: EventSpectrogramRequest,
    audio_path: Path,
    cache_path: Path,
    cfg: DetectionConfig | None = None,
) -> tuple[Path, float, float]:
    """Write (or reuse) the PNG for this table row. Returns path, t0, duration."""
    if cache_path.is_file() and cache_path.stat().st_size > 0:
        duration_s = audio_duration_s(audio_path)
        t0, win = event_context_window(
            req.start_s, req.end_s, duration_s, peak_time_s=req.peak_time_s
        )
        return cache_path, t0, win

    cfg = cfg or DetectionConfig()
    event = {
        "start_s": req.start_s,
        "end_s": req.end_s,
        "peak_time_s": req.peak_time_s,
        "peak_freq_hz": req.peak_freq_hz,
        "energy": 1.0,
        "n_callers": req.n_callers if req.n_callers is not None else 1,
    }
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = cache_path.with_suffix(".tmp.png")
    with _SPEC_LOCK:
        if cache_path.is_file() and cache_path.stat().st_size > 0:
            duration_s = audio_duration_s(audio_path)
            t0, win = event_context_window(
                req.start_s, req.end_s, duration_s, peak_time_s=req.peak_time_s
            )
            return cache_path, t0, win
        written = save_event_spectrogram(
            audio_path,
            event,
            cfg,
            tmp_path,
            filename=req.filename,
            event_n=req.event,
        )
        tmp_path.replace(cache_path)
    return cache_path, written.t0, written.duration_s


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


def make_handler(
    output_dir: Path,
    upload_dir: Path | None = None,
    field_dir: Path | None = None,
):
    output_dir = output_dir.resolve()
    upload_dir = (upload_dir or DEFAULT_UPLOAD_DIR).resolve()
    field_dir = (field_dir or DEFAULT_FIELD_DIR).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    upload_dir.mkdir(parents=True, exist_ok=True)
    audio_roots = (field_dir, output_dir, upload_dir)

    class DashboardHandler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args) -> None:  # noqa: A003
            print(f"[api] {self.address_string()} {format % args}")

        def _send(
            self,
            status: int,
            body: bytes,
            content_type: str,
            extra: dict[str, str] | None = None,
        ) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            headers = {"Cache-Control": "no-store"}
            if extra:
                headers.update(extra)
            for key, value in headers.items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(body)

        def do_OPTIONS(self) -> None:  # noqa: N802
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            path = unquote(parsed.path)
            query = parse_qs(parsed.query)
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

            if path in {"/api/event-spectrogram", "/api/event-spectrogram/"}:
                self._handle_event_spectrogram(query)
                return

            if path.startswith("/api/spectrograms/"):
                name = Path(path.removeprefix("/api/spectrograms/")).name
                if not name.endswith(".png"):
                    self._send(*_json_bytes({"error": "spectrogram must be a .png"}, 400))
                    return
                self._handle_file_spectrogram(name)
                return

            if path in {"/api/health", "/api/health/"}:
                self._send(*_json_bytes({"ok": True, "output": str(output_dir)}))
                return

            if path in {"/api/limits", "/api/limits/"}:
                self._send(*_json_bytes(limits_payload()))
                return

            self._send(*_json_bytes({"error": "not found"}, 404))

        def _handle_file_spectrogram(self, name: str) -> None:
            try:
                png = render_file_spectrogram(name, output_dir, audio_roots)
                body = png.read_bytes()
            except AnalyzeError as exc:
                payload: dict[str, str] = {"error": str(exc)}
                if exc.status == 404 and str(exc) == AUDIO_MISSING_MESSAGE:
                    payload["code"] = "audio_not_found"
                self._send(*_json_bytes(payload, exc.status))
                return
            except ValueError as exc:
                self._send(*_json_bytes({"error": str(exc)}, 400))
                return
            except Exception as exc:
                traceback.print_exc()
                self._send(*_json_bytes({"error": f"spectrogram failed: {exc}"}, 500))
                return
            self._send(
                200,
                body,
                "image/png",
                {"Cache-Control": "private, max-age=300", "X-Spectrogram-File": name},
            )

        def _handle_event_spectrogram(self, query: dict[str, list[str]]) -> None:
            try:
                req = parse_event_spectrogram_request(query)
            except AnalyzeError as exc:
                self._send(*_json_bytes({"error": str(exc)}, exc.status))
                return
            audio_path = find_audio_by_basename(req.filename, audio_roots)
            if audio_path is None:
                self._send(*_json_bytes(
                    {
                        "error": AUDIO_MISSING_MESSAGE,
                        "code": "audio_not_found",
                    },
                    404,
                ))
                return
            cache_path = event_spectrogram_cache_path(output_dir, req)
            try:
                png, t0, duration_s = render_event_spectrogram(req, audio_path, cache_path)
                body = png.read_bytes()
            except ValueError as exc:
                self._send(*_json_bytes({"error": str(exc)}, 400))
                return
            except Exception as exc:
                traceback.print_exc()
                self._send(*_json_bytes({"error": f"spectrogram failed: {exc}"}, 500))
                return
            extra = {
                "Cache-Control": "private, max-age=300",
                "X-Peak-Time-S": f"{req.peak_time_s:.6f}",
                "X-Peak-Freq-Hz": f"{req.peak_freq_hz:.3f}",
                "X-Window-Start-S": f"{t0:.6f}",
                "X-Window-Duration-S": f"{duration_s:.6f}",
                "X-Event-File": req.filename,
            }
            self._send(200, body, "image/png", extra)

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
    parser.add_argument("--field-dir", default=str(DEFAULT_FIELD_DIR))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    upload_dir = Path(args.upload_dir)
    field_dir = Path(args.field_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    upload_dir.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer((args.host, args.port), make_handler(output_dir, upload_dir, field_dir))
    print(f"Dashboard API at http://{args.host}:{args.port}/api/report")
    print(f"Upload/analyze at http://{args.host}:{args.port}/api/analyze")
    print(f"Event spectrogram at http://{args.host}:{args.port}/api/event-spectrogram")
    print(f"Reading outputs from {output_dir}; field audio from {field_dir}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping.")
        server.server_close()


if __name__ == "__main__":
    main()
