"""Slim the field-batch JSON so the Vite dashboard can load it without the API.

Reads gitignored ``output/resultado.json`` (~43 MB: 150k events + band_energy)
and writes ``web/public/campo/resultado.json``:

- full ``summary``, ``config``, ``by_hour``, ``by_month``
- full ``files`` rows without ``band_energy`` (not plotted in the UI)
- empty ``spectrogram`` (this batch ran with ``--no-spectrogram``)
- first ``PER_FILE`` events per file (the Excel report keeps every row)

Re-run after regenerating ``output/resultado.json``.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "output" / "resultado.json"
DEST = ROOT / "web" / "public" / "campo" / "resultado.json"
PER_FILE = 20


def slim_report(payload: dict) -> dict:
    files = []
    for row in payload["files"]:
        slim = {key: value for key, value in row.items() if key != "band_energy"}
        slim["spectrogram"] = ""
        files.append(slim)

    by_file: dict[str, list[dict]] = defaultdict(list)
    for event in payload["events"]:
        bucket = by_file[event["file"]]
        if len(bucket) < PER_FILE:
            bucket.append(event)

    sampled: list[dict] = []
    for row in files:
        sampled.extend(by_file.get(row["file"], []))

    n_total = int(payload["summary"]["n_events"])
    return {
        "generated_at": payload["generated_at"],
        "species": payload["species"],
        "common_name": payload["common_name"],
        "config": payload["config"],
        "summary": payload["summary"],
        "dashboard_source": "campo",
        "has_spectrograms": False,
        "events_sample": {
            "per_file": PER_FILE,
            "n_shown": len(sampled),
            "n_total": n_total,
        },
        "files": files,
        "events": sampled,
        "by_hour": payload["by_hour"],
        "by_month": payload["by_month"],
    }


def main() -> None:
    if not SOURCE.is_file():
        raise SystemExit(f"Missing {SOURCE} — run the field batch first.")

    with SOURCE.open(encoding="utf-8") as handle:
        payload = json.load(handle)

    dest_payload = slim_report(payload)
    DEST.parent.mkdir(parents=True, exist_ok=True)
    with DEST.open("w", encoding="utf-8") as handle:
        json.dump(dest_payload, handle, ensure_ascii=False, separators=(",", ":"))

    size_kb = DEST.stat().st_size / 1024
    print(
        f"Wrote {DEST} ({size_kb:.1f} KiB) — "
        f"{dest_payload['summary']['n_files']} files, "
        f"{dest_payload['summary']['n_events']} events in summary, "
        f"{dest_payload['events_sample']['n_shown']} events in table "
        f"({PER_FILE}/file)."
    )


if __name__ == "__main__":
    main()
