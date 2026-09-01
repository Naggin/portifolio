"""Tiny HTTP API so the React dashboard can read pipeline output.

Serves the JSON report and spectrogram PNGs from ``output/``. Run with:

    PYTHONPATH=src python -m bioacoustics.api
"""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

DEFAULT_OUTPUT = Path("output")
JSON_NAME = "resultado.json"


def _json_bytes(payload: object, status: int = 200) -> tuple[int, bytes, str]:
    return status, json.dumps(payload).encode("utf-8"), "application/json; charset=utf-8"


def make_handler(output_dir: Path):
    output_dir = output_dir.resolve()

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
            self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
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

            self._send(*_json_bytes({"error": "not found"}, 404))

    return DashboardHandler


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve detection reports for the dashboard.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer((args.host, args.port), make_handler(output_dir))
    print(f"Dashboard API at http://{args.host}:{args.port}/api/report")
    print(f"Reading outputs from {output_dir}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping.")
        server.server_close()


if __name__ == "__main__":
    main()
