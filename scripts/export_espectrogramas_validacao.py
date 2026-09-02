"""Gerar os PNG de validação da tese (recorte de escuta, não um PNG por evento).

Usa o WAV de campo e os eventos já contados em ``output/resultado.json``.
Não volta a correr o detector.

    python3 scripts/export_espectrogramas_validacao.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from bioacoustics.config import DetectionConfig  # noqa: E402
from bioacoustics.visualization import densest_window_start, save_spectrogram_window  # noqa: E402
from export_relatorio_provisorio import DEFAULT_SPEC_DIR, LISTEN  # noqa: E402

DEFAULT_WAV = ROOT / "data" / "field" / "10_10_25 açude 1" / "R20241012-041002.WAV"
DEFAULT_MORNING = ROOT / "data" / "field" / "10_10_25 açude 1" / "R20241012-091022.WAV"
DEFAULT_RESULTADO = ROOT / "output" / "resultado.json"
ZOOM_S = 8.0


def _events_for_file(payload: dict, filename: str) -> list[dict]:
    rows = [ev for ev in payload.get("events", []) if ev.get("file") == filename]
    rows.sort(key=lambda ev: float(ev["peak_time_s"]))
    return rows


def _duration(payload: dict, filename: str) -> float | None:
    for item in payload.get("files", []):
        if item.get("file") == filename:
            return float(item["duration_s"])
    return None


def generate_validation_pngs(
    resultado_path: Path,
    wav_path: Path,
    out_dir: Path,
    morning_path: Path | None = None,
) -> list[Path]:
    payload = json.loads(Path(resultado_path).read_text(encoding="utf-8"))
    cfg = DetectionConfig()
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    dawn_events = _events_for_file(payload, str(LISTEN["file"]))
    lo = float(LISTEN["start_s"])
    hi = float(LISTEN["end_s"])
    window_events = [
        ev for ev in dawn_events if lo <= float(ev["peak_time_s"]) < hi
    ]
    title_60 = (
        f"{LISTEN['file']} — {LISTEN['seek']}–{LISTEN['listen_until']} "
        f"(04:40) — picos de vocalização"
    )
    out_60 = out_dir / "R20241012-041002_30m45s.png"
    save_spectrogram_window(
        wav_path, window_events, lo, hi - lo, cfg, out_60, title_60
    )
    written.append(out_60)

    loudest = max(window_events, key=lambda ev: float(ev["energy"]))
    peak = float(loudest["peak_time_s"])
    freq = float(loudest["peak_freq_hz"])
    z0 = max(lo, peak - ZOOM_S / 2.0)
    if z0 + ZOOM_S > hi:
        z0 = max(lo, hi - ZOOM_S)
    title_zoom = (
        f"{LISTEN['file']} — zoom {ZOOM_S:.0f} s no pico mais forte "
        f"(~{peak:.0f} s, {freq / 1000:.2f} kHz)"
    )
    out_zoom = out_dir / f"R20241012-041002_pico_{peak:.0f}s.png"
    save_spectrogram_window(
        wav_path, window_events, z0, ZOOM_S, cfg, out_zoom, title_zoom
    )
    written.append(out_zoom)

    morning = Path(morning_path) if morning_path is not None else DEFAULT_MORNING
    if morning.is_file():
        mname = morning.name
        morning_events = _events_for_file(payload, mname)
        duration = _duration(payload, mname) or 0.0
        if morning_events and duration > 0:
            t0 = densest_window_start(
                morning_events, cfg.spectrogram_preview_s, duration
            )
            t1 = t0 + cfg.spectrogram_preview_s
            title_m = (
                f"{mname} — {_mmss(t0)}–{_mmss(t1)} — só depois da madrugada"
            )
            out_m = out_dir / "R20241012-091022_densest_60s.png"
            save_spectrogram_window(
                morning,
                morning_events,
                t0,
                cfg.spectrogram_preview_s,
                cfg,
                out_m,
                title_m,
            )
            written.append(out_m)
    return written


def _mmss(t: float) -> str:
    m, s = divmod(int(round(t)), 60)
    return f"{m}:{s:02d}"


def main(argv: list[str] | None = None) -> list[Path]:
    parser = argparse.ArgumentParser(
        description="PNG de validação (recorte 30:45), não um ficheiro por evento.",
    )
    parser.add_argument("--resultado", type=Path, default=DEFAULT_RESULTADO)
    parser.add_argument("--wav", type=Path, default=DEFAULT_WAV)
    parser.add_argument("--morning", type=Path, default=DEFAULT_MORNING)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_SPEC_DIR)
    args = parser.parse_args(argv)
    if not args.resultado.is_file():
        raise SystemExit(f"missing {args.resultado}")
    if not args.wav.is_file():
        raise SystemExit(f"missing {args.wav}")
    paths = generate_validation_pngs(
        args.resultado, args.wav, args.out_dir, morning_path=args.morning
    )
    for path in paths:
        print(f"wrote {path} ({path.stat().st_size / 1024:.0f} KiB)")
    return paths


if __name__ == "__main__":
    main()
