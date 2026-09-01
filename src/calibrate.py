"""CLI entrypoint: Phase 2 calibration from a clean reference recording.

Measures where the target species' call energy sits and recommends band-pass
edges and a detection threshold for :class:`DetectionConfig`. Wind (very low
frequencies) is excluded from the search so it can never anchor the band.

Examples:
    PYTHONPATH=src python src/calibrate.py "data/audios/CEAES 2.m4a"
    PYTHONPATH=src python src/calibrate.py ref.wav --output-dir output

Supported reference formats: .m4a, .wav, .flac, .ogg, .mp3 (m4a needs ffmpeg,
which librosa uses under the hood).
"""

from __future__ import annotations

import argparse
from pathlib import Path

from bioacoustics.audio_io import load_audio
from bioacoustics.calibration import (
    CalibrationConfig,
    analyze_reference,
    format_summary,
    save_calibration_plot,
    write_calibration_json,
)

_AUDIO_EXTS = {".m4a", ".wav", ".flac", ".ogg", ".mp3"}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Calibrate detection parameters from a reference recording."
    )
    parser.add_argument("reference", help="Clean reference audio of the species.")
    parser.add_argument("--output-dir", default="output", help="Where to write outputs.")
    parser.add_argument(
        "--plot-name",
        default="calibration_reference_band.png",
        help="Filename for the labeled reference spectrogram PNG.",
    )
    parser.add_argument(
        "--json-name",
        default="calibration.json",
        help="Filename for the recommended-config JSON (detect.py --config).",
    )
    parser.add_argument("--sample-rate", type=int, default=22_050, help="Analysis rate (Hz).")
    parser.add_argument("--n-fft", type=int, default=4_096, help="STFT window size.")
    parser.add_argument("--hop-length", type=int, default=1_024, help="STFT hop size.")
    parser.add_argument(
        "--wind-floor", type=float, default=300.0,
        help="Ignore energy below this frequency (Hz) as wind.",
    )
    parser.add_argument(
        "--band-db-down", type=float, default=12.0,
        help="Band edge threshold below the peak (dB).",
    )
    parser.add_argument("--no-plot", action="store_true", help="Skip PNG rendering.")
    parser.add_argument("--no-json", action="store_true", help="Skip JSON output.")
    args = parser.parse_args()

    ref = Path(args.reference)
    if not ref.exists():
        parser.error(f"Reference not found: {ref}")
    if ref.suffix.lower() not in _AUDIO_EXTS:
        parser.error(
            f"Unsupported format '{ref.suffix}'. Supported: {sorted(_AUDIO_EXTS)}"
        )

    cfg = CalibrationConfig(
        sample_rate=args.sample_rate,
        n_fft=args.n_fft,
        hop_length=args.hop_length,
        wind_floor_hz=args.wind_floor,
        band_db_down=args.band_db_down,
    )

    print(f"Loading reference: {ref}")
    y, _ = load_audio(ref, cfg.sample_rate)
    result = analyze_reference(y, cfg)

    print()
    print(format_summary(result, ref))
    print()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not args.no_plot:
        png = out_dir / args.plot_name
        save_calibration_plot(result, png, title=f"Calibration — {ref.name}")
        print(f"spectrogram  : {png}")

    if not args.no_json:
        js = out_dir / args.json_name
        write_calibration_json(result, cfg, js)
        print(f"config JSON  : {js}")
        print(f"\nApply it with:\n  PYTHONPATH=src python src/detect.py --config {js} <audio>")


if __name__ == "__main__":
    main()
