"""Spectrogram rendering for human validation (not used for counting)."""

from __future__ import annotations

from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")  # headless rendering
import matplotlib.pyplot as plt  # noqa: E402

from .config import DetectionConfig  # noqa: E402
from .detection import DetectionResult  # noqa: E402


def save_spectrogram(
    result: DetectionResult,
    cfg: DetectionConfig,
    out_path: str | Path,
    title: str = "Spectrogram with detected calls",
) -> Path:
    """Render the spectrogram with detected call peaks marked."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    fig, (ax_spec, ax_energy) = plt.subplots(
        2, 1, figsize=(12, 7), sharex=True, gridspec_kw={"height_ratios": [3, 1]}
    )

    spec_times = result.preview_times if result.preview_times is not None else result.times
    t0, t1 = float(spec_times[0]), float(spec_times[-1])
    extent = [t0, t1, result.freqs[0], result.freqs[-1]]
    ax_spec.imshow(
        result.spectrogram_db,
        aspect="auto",
        origin="lower",
        extent=extent,
        cmap="magma",
        vmin=-80,
        vmax=0,
    )
    ax_spec.axhline(cfg.lowcut_hz, color="cyan", ls="--", lw=0.8, alpha=0.7)
    ax_spec.axhline(cfg.highcut_hz, color="cyan", ls="--", lw=0.8, alpha=0.7)
    ax_spec.set_ylim(0, min(cfg.highcut_hz * 1.5, result.freqs[-1]))
    ax_spec.set_ylabel("Frequency (Hz)")
    ax_spec.set_title(title)

    visible = [ev for ev in result.events if t0 <= ev.peak_time_s <= t1]
    for ev in visible:
        ax_spec.plot(ev.peak_time_s, ev.peak_freq_hz, "o", color="lime", ms=6, mew=1.2,
                     markerfacecolor="none")
        ax_spec.axvspan(ev.start_s, ev.end_s, color="lime", alpha=0.08)

    # Energy trace: same window as the spectrogram so sharex stays readable
    # on multi-hour files (full-file energy still goes into the JSON report).
    mask = (result.times >= t0) & (result.times <= t1)
    if not np.any(mask):
        mask = np.ones(len(result.times), dtype=bool)
    ax_energy.plot(result.times[mask], result.band_energy[mask], color="steelblue", lw=0.8,
                   label="Band energy")
    ax_energy.axhline(result.threshold, color="red", ls="--", lw=1.0, label="Threshold")
    for ev in visible:
        ax_energy.axvline(ev.peak_time_s, color="lime", lw=0.6, alpha=0.6)
    ax_energy.set_xlabel("Time (s)")
    ax_energy.set_ylabel("Energy")
    ax_energy.legend(loc="upper right", fontsize=8)

    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)
    return out_path
