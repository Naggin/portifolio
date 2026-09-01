"""Excel report generation with per-event detail and hourly/monthly aggregates."""

from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook
from openpyxl.chart import BarChart, Reference

from .pipeline import PipelineResult


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
    counts: dict[int, int] = {h: 0 for h in range(24)}
    for r in results:
        if r.recorded_at is None:
            continue
        counts[r.recorded_at.hour] += r.detection.n_events

    ws.append(["hour", "n_events"])
    for h in range(24):
        ws.append([h, counts[h]])

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
    counts: dict[int, int] = {m: 0 for m in range(1, 13)}
    for r in results:
        if r.recorded_at is None:
            continue
        counts[r.recorded_at.month] += r.detection.n_events

    ws.append(["month", "n_events"])
    for m in range(1, 13):
        ws.append([m, counts[m]])

    chart = BarChart()
    chart.title = "Calls by month"
    chart.x_axis.title = "Month"
    chart.y_axis.title = "Calls"
    data = Reference(ws, min_col=2, min_row=1, max_row=13)
    cats = Reference(ws, min_col=1, min_row=2, max_row=13)
    chart.add_data(data, titles_from_data=True)
    chart.set_categories(cats)
    ws.add_chart(chart, "D2")
