"""Generate a synthetic test recording that mimics the field data.

Real field recordings are ~5 GB of 1-hour WAVs that we cannot ship in the repo.
This script synthesizes a short clip containing:

  * Several Sphaenorhynchus-like calls (short chirps in the 2.5-3 kHz band).
  * A stretch where two individuals call simultaneously at different pitches.
  * Strong low-frequency wind noise (the main real-world nuisance).
  * Broadband background hiss.

It lets us exercise and demonstrate the full pipeline end to end without the
real audio. The filename embeds a date/time like the real recorder does.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import soundfile as sf


def _chirp(t: np.ndarray, f0: float, f1: float, amp: float) -> np.ndarray:
    """A short frequency-swept tone shaped by a smooth envelope."""
    k = (f1 - f0) / t[-1]
    phase = 2 * np.pi * (f0 * t + 0.5 * k * t**2)
    env = np.hanning(len(t))
    return amp * env * np.sin(phase)


def synthesize(sr: int = 22_050, duration_s: float = 30.0, seed: int = 42) -> np.ndarray:
    rng = np.random.default_rng(seed)
    n = int(sr * duration_s)
    audio = np.zeros(n, dtype=np.float32)

    # --- Wind: strong low-frequency, amplitude-modulated rumble ---
    t_full = np.arange(n) / sr
    wind = 0.35 * np.sin(2 * np.pi * 80 * t_full) * (0.5 + 0.5 * np.sin(2 * np.pi * 0.3 * t_full))
    wind += 0.2 * np.sin(2 * np.pi * 150 * t_full)
    audio += wind.astype(np.float32)

    # --- Broadband background hiss ---
    audio += (0.01 * rng.standard_normal(n)).astype(np.float32)

    def place(center_s: float, dur_s: float, f0: float, f1: float, amp: float) -> None:
        start = int(center_s * sr)
        length = int(dur_s * sr)
        if start + length > n:
            length = n - start
        t = np.arange(length) / sr
        audio[start : start + length] += _chirp(t, f0, f1, amp).astype(np.float32)

    # --- Individual A: single calls (peak ~2.7 kHz) ---
    for center in [2.0, 5.0, 8.5, 12.0, 20.0, 24.0, 27.5]:
        place(center, 0.25, 2600, 2800, 0.5)

    # --- Overlap: A + a second individual B (~3.3 kHz) around 15-16 s ---
    place(15.0, 0.25, 2600, 2750, 0.5)   # individual A (~2.7 kHz, species-like)
    place(15.1, 0.25, 3050, 3180, 0.45)  # individual B (~3.1 kHz, still in-band)

    # Normalize to avoid clipping.
    peak = float(np.max(np.abs(audio))) or 1.0
    audio = (audio / peak * 0.9).astype(np.float32)
    return audio


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a synthetic test recording.")
    parser.add_argument(
        "-o", "--output",
        default="data/audios/R20241011-180923.WAV",
        help="Output WAV path (filename encodes date/time like the real recorder).",
    )
    parser.add_argument("--duration", type=float, default=30.0)
    parser.add_argument("--sample-rate", type=int, default=22_050)
    args = parser.parse_args()

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    audio = synthesize(sr=args.sample_rate, duration_s=args.duration)
    sf.write(str(out), audio, args.sample_rate, subtype="PCM_16")
    print(f"Wrote synthetic recording: {out} ({args.duration:.0f}s @ {args.sample_rate} Hz)")


if __name__ == "__main__":
    main()
