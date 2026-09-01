"""CLI entrypoint: run the detection pipeline over one or more recordings.

Examples:
    python src/detect.py data/audios/R20241011-180923.WAV
    python src/detect.py data/audios/            # process every WAV in a folder
"""

from __future__ import annotations

import argparse
from pathlib import Path

from bioacoustics.config import AUDIO_EXTENSIONS, DetectionConfig
from bioacoustics.pipeline import PipelineResult, process_file
from bioacoustics.report import write_json_report, write_report
from bioacoustics.visualization import save_spectrogram

_AUDIO_EXTS = set(AUDIO_EXTENSIONS)


def _gather_inputs(inputs: list[str]) -> list[Path]:
    paths: list[Path] = []
    for item in inputs:
        p = Path(item)
        if p.is_dir():
            paths.extend(sorted(f for f in p.rglob("*") if f.suffix.lower() in _AUDIO_EXTS))
        elif p.suffix.lower() in _AUDIO_EXTS:
            paths.append(p)
    return paths


def main() -> None:
    parser = argparse.ArgumentParser(description="Detect and count frog vocalizations.")
    parser.add_argument("inputs", nargs="+", help="Audio file(s) or folder(s).")
    parser.add_argument("--output-dir", default="output", help="Where to write outputs.")
    parser.add_argument("--no-spectrogram", action="store_true", help="Skip PNG rendering.")
    parser.add_argument("--report", default="resultado.xlsx", help="Excel report filename.")
    parser.add_argument("--json-report", default="resultado.json", help="JSON report filename.")
    parser.add_argument("--lowcut", type=float, help="Band-pass low cut (Hz).")
    parser.add_argument("--highcut", type=float, help="Band-pass high cut (Hz).")
    parser.add_argument("--threshold-k", type=float, help="Detection threshold multiplier.")
    args = parser.parse_args()

    cfg = DetectionConfig()
    if args.lowcut is not None:
        cfg.lowcut_hz = args.lowcut
    if args.highcut is not None:
        cfg.highcut_hz = args.highcut
    if args.threshold_k is not None:
        cfg.threshold_k = args.threshold_k

    paths = _gather_inputs(args.inputs)
    if not paths:
        parser.error("No audio files found in the given inputs.")

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    results: list[PipelineResult] = []
    for path in paths:
        print(f"\nProcessing {path} ...")
        r = process_file(path, cfg)
        results.append(r)
        recorded = r.recorded_at.isoformat(sep=" ") if r.recorded_at else "unknown"
        print(f"  recorded at : {recorded}")
        print(f"  duration    : {r.detection.duration_s:.1f} s")
        print(f"  calls found : {r.detection.n_events}")
        print(f"  max simult. : {r.detection.max_simultaneous} individual(s)")
        for i, ev in enumerate(r.detection.events, start=1):
            if i > 15:
                print(f"    ... {r.detection.n_events - 15} more events")
                break
            print(
                f"    #{i:>2}  t={ev.peak_time_s:6.2f}s  "
                f"f={ev.peak_freq_hz:6.0f}Hz  dur={ev.duration_s:.2f}s"
            )

        if not args.no_spectrogram:
            png = out_dir / f"{path.stem}_spectrogram.png"
            save_spectrogram(r.detection, cfg, png, title=f"{path.name} — detected calls")
            print(f"  spectrogram : {png}")

    report_path = out_dir / args.report
    write_report(results, report_path)
    json_path = out_dir / args.json_report
    write_json_report(results, json_path, cfg)
    print(f"\nReport written: {report_path}")
    print(f"JSON report   : {json_path}")
    total = sum(r.detection.n_events for r in results)
    print(f"Total files: {len(results)}  |  total calls: {total}")


if __name__ == "__main__":
    main()
