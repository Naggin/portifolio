"""Build a git-friendly summary from output/resultado.json + analyze.log."""

from __future__ import annotations

import json
import re
import statistics
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output"
REPORTS = ROOT / "reports"
JSON_IN = OUT / "resultado.json"
LOG = OUT / "analyze.log"
JSON_OUT = REPORTS / "campo_resumo.json"

PROCESSING_RE = re.compile(r"^Processing (data/field/(.+)/([^/]+)) \.\.\.\s*$")


def _pct(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    if len(s) == 1:
        return round(s[0], 3)
    k = (len(s) - 1) * p / 100.0
    lo = int(k)
    hi = min(lo + 1, len(s) - 1)
    frac = k - lo
    return round(s[lo] * (1 - frac) + s[hi] * frac, 3)


def _campaign_from_log() -> dict[str, str]:
    """Map basename -> campaign folder (from detect.py log)."""
    mapping: dict[str, str] = {}
    if not LOG.exists():
        return mapping
    for line in LOG.read_text(encoding="utf-8", errors="replace").splitlines():
        m = PROCESSING_RE.match(line)
        if m:
            mapping[m.group(3)] = m.group(2)
    return mapping


def _hist(values: list[float], start: float, stop: float, step: float) -> list[dict]:
    bins: list[dict] = []
    x = start
    while x < stop - 1e-9:
        bins.append({"lo": x, "hi": round(x + step, 6), "n": 0})
        x += step
    for v in values:
        i = int((v - start) / step)
        if i < 0:
            i = 0
        if i >= len(bins):
            i = len(bins) - 1
        bins[i]["n"] += 1
    return bins


def main() -> None:
    data = json.loads(JSON_IN.read_text(encoding="utf-8"))
    camp_map = _campaign_from_log()

    files_out = []
    by_campaign: dict[str, dict] = {}
    n_no_date = 0
    events_no_date = 0

    for f in data["files"]:
        name = f["file"]
        campaign = camp_map.get(name, "(sem pasta)")
        duration_s = float(f["duration_s"])
        n_events = int(f["n_events"])
        eph = n_events / (duration_s / 3600.0) if duration_s > 0 else 0.0
        rec = f.get("recorded_at")
        if not rec:
            n_no_date += 1
            events_no_date += n_events
        row = {
            "campaign": campaign,
            "file": name,
            "recorded_at": rec,
            "duration_s": round(duration_s, 3),
            "n_events": n_events,
            "max_simultaneous": int(f["max_simultaneous"]),
            "events_per_hour": round(eph, 1),
            "threshold": f.get("threshold"),
        }
        files_out.append(row)
        agg = by_campaign.setdefault(
            campaign,
            {
                "campaign": campaign,
                "n_files": 0,
                "n_events": 0,
                "total_duration_s": 0.0,
                "max_simultaneous": 0,
                "n_without_recorded_at": 0,
            },
        )
        agg["n_files"] += 1
        agg["n_events"] += n_events
        agg["total_duration_s"] += duration_s
        agg["max_simultaneous"] = max(agg["max_simultaneous"], int(f["max_simultaneous"]))
        if not rec:
            agg["n_without_recorded_at"] += 1

    campaigns = []
    for campaign in sorted(by_campaign):
        agg = by_campaign[campaign]
        dur = agg["total_duration_s"]
        agg["total_duration_h"] = round(dur / 3600.0, 3)
        agg["total_duration_s"] = round(dur, 3)
        agg["events_per_hour"] = round(agg["n_events"] / (dur / 3600.0), 1) if dur else 0.0
        campaigns.append(agg)

    freqs = [float(e["peak_freq_hz"]) for e in data["events"]]
    durs = [float(e["duration_s"]) for e in data["events"]]
    callers = [int(e["n_callers"]) for e in data["events"]]
    caller_counts: dict[str, int] = defaultdict(int)
    for c in callers:
        caller_counts[str(c)] += 1

    summary = dict(data["summary"])
    total_s = float(summary["total_duration_s"])
    summary["total_duration_h"] = round(total_s / 3600.0, 3)
    summary["events_per_hour"] = round(summary["n_events"] / (total_s / 3600.0), 1)
    summary["n_errors"] = 0
    summary["n_files_without_recorded_at"] = n_no_date
    summary["n_events_without_recorded_at"] = events_no_date
    summary["n_events_in_by_hour_by_month"] = int(summary["n_events"]) - events_no_date

    wav_eph = [f["events_per_hour"] for f in files_out if f["file"].lower().endswith(".wav")]
    mp3_eph = [f["events_per_hour"] for f in files_out if f["file"].lower().endswith(".mp3")]

    payload = {
        "generated_from": "output/resultado.json",
        "pipeline_generated_at": data.get("generated_at"),
        "species": data.get("species"),
        "common_name": data.get("common_name"),
        "config": data.get("config"),
        "command": (
            "PYTHONPATH=src python3 src/detect.py data/field "
            "--no-spectrogram --output-dir output "
            "--report resultado.xlsx --json-report resultado.json"
        ),
        "skipped_drive_folders": [
            "15/08 açude 2 (esse nao precisa)",
            "Áudio base",
        ],
        "artifacts": {
            "xlsx": "output/resultado.xlsx (gitignored, ~7 MB)",
            "json": "output/resultado.json (gitignored, ~43 MB; events + band_energy)",
            "log": "output/analyze.log",
            "dashboard": (
                "PYTHONPATH=src python -m bioacoustics.api  "
                "and  cd web && npm run dev  "
                "(GET /api/report reads output/resultado.json)"
            ),
        },
        "summary": summary,
        "wav_events_per_hour": {
            "n": len(wav_eph),
            "min": round(min(wav_eph), 1) if wav_eph else None,
            "median": round(statistics.median(wav_eph), 1) if wav_eph else None,
            "max": round(max(wav_eph), 1) if wav_eph else None,
        },
        "mp3_events_per_hour": {
            "n": len(mp3_eph),
            "min": round(min(mp3_eph), 1) if mp3_eph else None,
            "median": round(statistics.median(mp3_eph), 1) if mp3_eph else None,
            "max": round(max(mp3_eph), 1) if mp3_eph else None,
        },
        "peak_freq_hz": {
            "min": round(min(freqs), 1) if freqs else None,
            "p25": _pct(freqs, 25),
            "median": _pct(freqs, 50),
            "p75": _pct(freqs, 75),
            "max": round(max(freqs), 1) if freqs else None,
            "hist_100hz": _hist(freqs, 2600.0, 3200.0, 100.0),
        },
        "event_duration_s": {
            "min": round(min(durs), 3) if durs else None,
            "p25": _pct(durs, 25),
            "median": _pct(durs, 50),
            "p75": _pct(durs, 75),
            "max": round(max(durs), 3) if durs else None,
        },
        "n_callers": dict(sorted(caller_counts.items(), key=lambda kv: int(kv[0]))),
        "caveats": [
            (
                "Mediana nos WAV: ~1 600 eventos/hora (mín. 315, máx. 3 014). "
                "Isso pode incluir ruído/insetos na banda 2,6–3,2 kHz; a "
                "calibração foi no recorte limpo CEAES 2, não no campo ruidoso."
            ),
            (
                "max_simultaneous=2 em todos os arquivos é também um teto "
                "estrutural: banda de 600 Hz com freq_separation_hz=400 Hz "
                "cabe no máximo ~2 picos distintos."
            ),
            (
                "7 MP3s (campanhas 12_09_25 e 15_08_25) não têm recorded_at "
                "no nome; seus eventos entram no total mas não em by_hour/"
                "by_month (agosto/setembro ficam de fora desses gráficos)."
            ),
            (
                "Agregados por hora usam a hora do INÍCIO do arquivo, não o "
                "instante de cada evento."
            ),
            "Este lote rodou com --no-spectrogram; não há PNG por arquivo.",
        ],
        "campaigns": campaigns,
        "files": files_out,
        "by_hour": data.get("by_hour"),
        "by_month": data.get("by_month"),
        "errors": [],
    }

    REPORTS.mkdir(parents=True, exist_ok=True)
    JSON_OUT.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {JSON_OUT} ({JSON_OUT.stat().st_size} bytes)")
    print(
        f"files={summary['n_files']} events={summary['n_events']} "
        f"hours={summary['total_duration_h']} eph={summary['events_per_hour']}"
    )


if __name__ == "__main__":
    main()
