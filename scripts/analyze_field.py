"""Run detection on every field recording, resuming if interrupted."""

from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from bioacoustics.config import AUDIO_EXTENSIONS, DetectionConfig  # noqa: E402
from bioacoustics.pipeline import process_file  # noqa: E402
from bioacoustics.report import write_json_report, write_report  # noqa: E402

FIELD = ROOT / "data" / "field"
OUT = ROOT / "output"
PROGRESS = OUT / "analyze_progress.json"


def _load_progress() -> dict:
    if PROGRESS.exists():
        return json.loads(PROGRESS.read_text())
    return {"done": {}, "errors": {}}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    files = sorted(
        p for p in FIELD.rglob("*") if p.suffix.lower() in AUDIO_EXTENSIONS
    )
    if not files:
        raise SystemExit(f"no audio under {FIELD}")
    progress = _load_progress()
    cfg = DetectionConfig()
    results = []
    # Re-run already-done files from progress only if we still have the objects;
    # we always recompute from scratch for the final report, but skip process_file
    # when the path is in progress["done"] by loading nothing — actually we need
    # PipelineResult objects. Simplest: skip files already in done and process
    # remaining, then we cannot rebuild full report without re-processing.
    # So: process remaining only, then if we want a full report we must either
    # store per-file JSON or reprocess. Store per-file sidecar JSON.
    for i, path in enumerate(files, 1):
        rel = str(path.relative_to(FIELD))
        sidecar = OUT / "per_file" / (path.stem + ".ok")
        sidecar.parent.mkdir(parents=True, exist_ok=True)
        print(f"\n[{i}/{len(files)}] {rel}", flush=True)
        if sidecar.exists() and rel in progress.get("done", {}):
            print(f"  skip (already done: {progress['done'][rel]})", flush=True)
            continue
        try:
            r = process_file(path, cfg)
            info = {
                "file": rel,
                "recorded_at": r.recorded_at.isoformat() if r.recorded_at else None,
                "duration_s": r.detection.duration_s,
                "n_events": r.detection.n_events,
                "max_simultaneous": r.detection.max_simultaneous,
            }
            progress["done"][rel] = info
            sidecar.write_text(json.dumps(info, indent=2))
            PROGRESS.write_text(json.dumps(progress, indent=2))
            print(
                f"  duration={r.detection.duration_s/3600:.2f}h  "
                f"calls={r.detection.n_events}  maxsim={r.detection.max_simultaneous}",
                flush=True,
            )
            results.append(r)
        except Exception as exc:  # noqa: BLE001
            progress.setdefault("errors", {})[rel] = f"{type(exc).__name__}: {exc}"
            PROGRESS.write_text(json.dumps(progress, indent=2))
            print(f"  ERROR {exc}", flush=True)
            traceback.print_exc()

    # Final pass: process any file not yet in results (skipped) by running again
    # only if results is incomplete. For a complete xlsx/json we re-process skipped
    # cheaply... no, that's hours. Instead after all files are in progress["done"],
    # write a summary JSON from progress and a second full pipeline only if all
    # results were collected this run.
    summary = {
        "n_files": len(progress.get("done", {})),
        "n_errors": len(progress.get("errors", {})),
        "n_events": sum(v["n_events"] for v in progress.get("done", {}).values()),
        "files": progress.get("done", {}),
        "errors": progress.get("errors", {}),
    }
    (OUT / "resumo_campo.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print("\n=== summary ===", flush=True)
    print(json.dumps(summary, indent=2, ensure_ascii=False)[:4000], flush=True)

    if results:
        # Partial report for this process run (newly processed files).
        write_json_report(results, OUT / "resultado_parcial.json", cfg)
        write_report(results, OUT / "resultado_parcial.xlsx")
        print(f"partial report: {len(results)} files this invocation", flush=True)


if __name__ == "__main__":
    main()
