"""Excel and JSON report generation with per-event detail and hourly/monthly aggregates."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from openpyxl import Workbook
from openpyxl.chart import BarChart, Reference

from .config import DetectionConfig
from .pipeline import PipelineResult

SPECIES_NAME = "Sphaenorhynchus caramaschii"
SPECIES_COMMON_NAME = "perereca-de-banhado"
ENERGY_SERIES_POINTS = 400


def _hourly_counts(results: list[PipelineResult]) -> list[dict[str, int]]:
    counts: dict[int, int] = {h: 0 for h in range(24)}
    for r in results:
        if r.recorded_at is None:
            continue
        counts[r.recorded_at.hour] += r.detection.n_events
    return [{"hour": h, "n_events": counts[h]} for h in range(24)]


def _monthly_counts(results: list[PipelineResult]) -> list[dict[str, int]]:
    counts: dict[int, int] = {m: 0 for m in range(1, 13)}
    for r in results:
        if r.recorded_at is None:
            continue
        counts[r.recorded_at.month] += r.detection.n_events
    return [{"month": m, "n_events": counts[m]} for m in range(1, 13)]


def _downsample_series(values: list[float], times: list[float], max_points: int) -> dict[str, list[float]]:
    if len(values) <= max_points:
        return {"times_s": [round(t, 3) for t in times], "energy": [round(v, 4) for v in values]}
    step = max(1, len(values) // max_points)
    idx = list(range(0, len(values), step))
    if idx[-1] != len(values) - 1:
        idx.append(len(values) - 1)
    return {
        "times_s": [round(times[i], 3) for i in idx],
        "energy": [round(values[i], 4) for i in idx],
    }


def _file_payload(result: PipelineResult) -> dict[str, Any]:
    recorded = result.recorded_at.isoformat() if result.recorded_at else None
    times = result.detection.times.tolist()
    energy = result.detection.band_energy.tolist()
    return {
        "file": result.filename,
        "recorded_at": recorded,
        "duration_s": round(result.detection.duration_s, 3),
        "n_events": result.detection.n_events,
        "max_simultaneous": result.detection.max_simultaneous,
        "threshold": round(float(result.detection.threshold), 6),
        "spectrogram": f"{Path(result.filename).stem}_spectrogram.png",
        "band_energy": _downsample_series(energy, times, ENERGY_SERIES_POINTS),
    }


def _event_payloads(result: PipelineResult) -> list[dict[str, Any]]:
    recorded = result.recorded_at.isoformat() if result.recorded_at else None
    rows: list[dict[str, Any]] = []
    for i, ev in enumerate(result.detection.events, start=1):
        rows.append({
            "file": result.filename,
            "recorded_at": recorded,
            "event": i,
            "start_s": round(ev.start_s, 3),
            "end_s": round(ev.end_s, 3),
            "peak_time_s": round(ev.peak_time_s, 3),
            "peak_freq_hz": round(ev.peak_freq_hz, 1),
            "energy": round(ev.energy, 3),
            "n_callers": ev.n_callers,
            "duration_s": round(ev.duration_s, 3),
        })
    return rows


def build_report_payload(
    results: list[PipelineResult],
    cfg: DetectionConfig | None = None,
) -> dict[str, Any]:
    """Serialize pipeline results into the dashboard JSON contract."""
    cfg = cfg or DetectionConfig()
    files = [_file_payload(r) for r in results]
    events = [row for r in results for row in _event_payloads(r)]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "species": SPECIES_NAME,
        "common_name": SPECIES_COMMON_NAME,
        "config": {
            "sample_rate": cfg.sample_rate,
            "lowcut_hz": cfg.lowcut_hz,
            "highcut_hz": cfg.highcut_hz,
            "threshold_k": cfg.threshold_k,
        },
        "summary": {
            "n_files": len(results),
            "n_events": sum(r.detection.n_events for r in results),
            "max_simultaneous": max((r.detection.max_simultaneous for r in results), default=0),
            "total_duration_s": round(sum(r.detection.duration_s for r in results), 3),
        },
        "files": files,
        "events": events,
        "by_hour": _hourly_counts(results),
        "by_month": _monthly_counts(results),
    }


def write_json_report(
    results: list[PipelineResult],
    out_path: str | Path,
    cfg: DetectionConfig | None = None,
) -> Path:
    """Write the dashboard JSON report next to the Excel workbook."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = build_report_payload(results, cfg)
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return out_path


def write_report(results: list[PipelineResult], out_path: str | Path) -> Path:
    """Write a multi-sheet .xlsx summarizing detections across files."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    wb = Workbook()

    _write_events_sheet(wb.active, results)
    _write_files_sheet(wb.create_sheet("Files"), results)
    _write_hourly_sheet(wb.create_sheet("By hour"), results)
    _write_monthly_sheet(wb.create_sheet("By month"), results)

    wb.save(out_path)
    return out_path


def _write_events_sheet(ws, results: list[PipelineResult]) -> None:
    ws.title = "Events"
    ws.append([
        "file", "recorded_at", "event", "start_s", "end_s",
        "peak_time_s", "peak_freq_hz", "energy", "n_callers",
    ])
    for r in results:
        recorded = r.recorded_at.isoformat() if r.recorded_at else ""
        for i, ev in enumerate(r.detection.events, start=1):
            ws.append([
                r.filename, recorded, i,
                round(ev.start_s, 3), round(ev.end_s, 3),
                round(ev.peak_time_s, 3), round(ev.peak_freq_hz, 1),
                round(ev.energy, 3), ev.n_callers,
            ])


def _write_files_sheet(ws, results: list[PipelineResult]) -> None:
    ws.append([
        "file", "recorded_at", "duration_s", "n_events", "max_simultaneous",
    ])
    for r in results:
        recorded = r.recorded_at.isoformat() if r.recorded_at else ""
        ws.append([
            r.filename, recorded, round(r.detection.duration_s, 1),
            r.detection.n_events, r.detection.max_simultaneous,
        ])


def _write_hourly_sheet(ws, results: list[PipelineResult]) -> None:
    ws.append(["hour", "n_events"])
    for row in _hourly_counts(results):
        ws.append([row["hour"], row["n_events"]])

    chart = BarChart()
    chart.title = "Calls by hour of day"
    chart.x_axis.title = "Hour"
    chart.y_axis.title = "Calls"
    data = Reference(ws, min_col=2, min_row=1, max_row=25)
    cats = Reference(ws, min_col=1, min_row=2, max_row=25)
    chart.add_data(data, titles_from_data=True)
    chart.set_categories(cats)
    ws.add_chart(chart, "D2")


def _write_monthly_sheet(ws, results: list[PipelineResult]) -> None:
    ws.append(["month", "n_events"])
    for row in _monthly_counts(results):
        ws.append([row["month"], row["n_events"]])

    chart = BarChart()
    chart.title = "Calls by month"
    chart.x_axis.title = "Month"
    chart.y_axis.title = "Calls"
    data = Reference(ws, min_col=2, min_row=1, max_row=13)
    cats = Reference(ws, min_col=1, min_row=2, max_row=13)
    chart.add_data(data, titles_from_data=True)
    chart.set_categories(cats)
    ws.add_chart(chart, "D2")
