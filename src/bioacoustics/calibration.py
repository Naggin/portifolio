"""Phase 2 calibration: derive detection parameters from a reference recording.

Given a clean recording that clearly contains the target species, this module
measures where the call energy actually sits in frequency and recommends
concrete :class:`DetectionConfig` values (band-pass edges and detection
sensitivity). The goal is to tune ``lowcut_hz``/``highcut_hz`` tightly around
the real call band so that low-frequency wind can never become a false positive.

The measurement is done on the numeric spectrogram (never on an image):
  1. Average the STFT power across time into a mean power spectrum.
  2. Ignore very low frequencies (< ``wind_floor_hz``) which are wind, not calls.
  3. Take the dominant peak and grow a band around it down to ``band_db_down``
     dB below the peak (and, independently, the band holding the bulk of the
     in-band energy).
  4. Add a margin and round to recommend band-pass edges, and derive a
     data-driven ``threshold_k`` from how far call frames stand above the floor.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .config import DetectionConfig


@dataclass
class CalibrationConfig:
    # --- Loading ---
    sample_rate: int = 22_050  # Hz; the reference is downsampled on load.

    # --- Spectrogram (finer than detection for accurate band edges) ---
    n_fft: int = 4_096
    hop_length: int = 1_024

    # --- Band measurement ---
    # Frequencies below this are treated as wind and excluded from the search
    # for the dominant call band.
    wind_floor_hz: float = 300.0
    # Band edges are placed where the mean power drops this many dB below peak.
    band_db_down: float = 12.0
    # Independent estimate: the smallest band around the peak holding this
    # fraction of the total in-band energy.
    energy_fraction: float = 0.90

    # --- Recommendation margins ---
    # Extra room added on each side of the measured band before recommending
    # band-pass edges (fractional, relative to the measured edge, with a floor).
    margin_frac: float = 0.15
    min_margin_hz: float = 200.0
    # Recommended edges are rounded to this grid (Hz) for tidy config values.
    round_to_hz: float = 50.0
    # Suggested threshold multiplier is clamped to this sane range.
    threshold_k_bounds: tuple[float, float] = (4.0, 8.0)

    @property
    def nyquist(self) -> float:
        return self.sample_rate / 2.0


@dataclass
class CalibrationResult:
    sample_rate: int
    duration_s: float

    # Measured band (Hz).
    peak_freq_hz: float
    band_low_hz: float          # edges at ``band_db_down`` below the peak.
    band_high_hz: float
    energy_band_low_hz: float   # edges enclosing ``energy_fraction`` of energy.
    energy_band_high_hz: float

    # Recommended DetectionConfig values.
    recommended_lowcut_hz: float
    recommended_highcut_hz: float
    recommended_threshold_k: float

    # Quality diagnostics.
    in_band_snr_db: float

    # Arrays kept for plotting / debugging (not serialized).
    freqs: np.ndarray = field(repr=False)
    mean_power_db: np.ndarray = field(repr=False)
    spectrogram_db: np.ndarray = field(repr=False)
    times: np.ndarray = field(repr=False)

    def recommended_config(self, base: DetectionConfig | None = None) -> DetectionConfig:
        """Return a :class:`DetectionConfig` with the recommended band applied."""
        cfg = base or DetectionConfig()
        cfg.lowcut_hz = self.recommended_lowcut_hz
        cfg.highcut_hz = self.recommended_highcut_hz
        cfg.threshold_k = self.recommended_threshold_k
        return cfg

    def to_dict(self) -> dict:
        """Serializable summary (no numpy arrays) for ``calibration.json``."""
        return {
            "sample_rate": self.sample_rate,
            "duration_s": round(self.duration_s, 3),
            "measured": {
                "peak_freq_hz": round(self.peak_freq_hz, 1),
                "band_low_hz": round(self.band_low_hz, 1),
                "band_high_hz": round(self.band_high_hz, 1),
                "energy_band_low_hz": round(self.energy_band_low_hz, 1),
                "energy_band_high_hz": round(self.energy_band_high_hz, 1),
                "in_band_snr_db": round(self.in_band_snr_db, 1),
            },
            "recommended": {
                "lowcut_hz": round(self.recommended_lowcut_hz, 1),
                "highcut_hz": round(self.recommended_highcut_hz, 1),
                "threshold_k": round(self.recommended_threshold_k, 2),
            },
        }


def _round_to(value: float, grid: float) -> float:
    if grid <= 0:
        return value
    return float(round(value / grid) * grid)


def _mean_power_spectrum(magnitude: np.ndarray) -> np.ndarray:
    """Average STFT power across time frames -> one power value per bin."""
    return (magnitude.astype(np.float64) ** 2).mean(axis=1)


def _db_band_edges(
    freqs: np.ndarray, power: np.ndarray, peak_idx: int, db_down: float
) -> tuple[float, float]:
    """Grow a contiguous band around ``peak_idx`` down to ``db_down`` below peak."""
    floor = power[peak_idx] * (10.0 ** (-db_down / 10.0))
    lo = peak_idx
    while lo > 0 and power[lo - 1] >= floor:
        lo -= 1
    hi = peak_idx
    while hi < len(power) - 1 and power[hi + 1] >= floor:
        hi += 1
    return float(freqs[lo]), float(freqs[hi])


def _energy_band_edges(
    freqs: np.ndarray, power: np.ndarray, peak_idx: int, fraction: float
) -> tuple[float, float]:
    """Smallest band around the peak holding ``fraction`` of the total power."""
    total = float(power.sum()) or 1e-12
    target = fraction * total
    lo = hi = peak_idx
    acc = float(power[peak_idx])
    while acc < target and (lo > 0 or hi < len(power) - 1):
        left = power[lo - 1] if lo > 0 else -np.inf
        right = power[hi + 1] if hi < len(power) - 1 else -np.inf
        if right >= left:
            hi += 1
            acc += float(power[hi])
        else:
            lo -= 1
            acc += float(power[lo])
    return float(freqs[lo]), float(freqs[hi])


def _recommend_threshold_k(snr_db: float, bounds: tuple[float, float]) -> float:
    """Map in-band SNR to a starting ``k`` for the median + k·MAD threshold.

    A clean reference has almost no in-band noise, so a frame-level threshold
    fitted to it would be arbitrarily high; the binding constraint (wind /
    background) only appears in the field. We therefore derive a *starting*
    multiplier from the reference's in-band SNR — a louder, cleaner call band
    tolerates a higher threshold while still catching the call — and clamp it to
    a field-sane range. It should be validated on real recordings.
    """
    lo, hi = bounds
    k = 4.0 + (snr_db - 10.0) / 6.0
    return float(np.clip(k, lo, hi))


def analyze_reference(y: np.ndarray, cfg: CalibrationConfig) -> CalibrationResult:
    """Measure the dominant call band and recommend detection parameters."""
    import librosa

    stft = librosa.stft(y, n_fft=cfg.n_fft, hop_length=cfg.hop_length)
    magnitude = np.abs(stft)
    freqs = librosa.fft_frequencies(sr=cfg.sample_rate, n_fft=cfg.n_fft)
    times = librosa.frames_to_time(
        np.arange(magnitude.shape[1]), sr=cfg.sample_rate, hop_length=cfg.hop_length
    )

    power = _mean_power_spectrum(magnitude)

    # Restrict the peak search to above the wind floor.
    search = freqs >= cfg.wind_floor_hz
    if not search.any():
        raise ValueError(
            f"No frequency bins above wind_floor_hz={cfg.wind_floor_hz} Hz; "
            "check sample_rate / n_fft."
        )
    search_idx = np.flatnonzero(search)
    peak_idx = int(search_idx[np.argmax(power[search_idx])])
    peak_freq = float(freqs[peak_idx])

    # Measure band edges within the above-wind region only, so the search
    # cannot leak down into the wind band.
    lo_bound = int(search_idx[0])
    sub_freqs = freqs[lo_bound:]
    sub_power = power[lo_bound:]
    sub_peak = peak_idx - lo_bound
    band_low, band_high = _db_band_edges(sub_freqs, sub_power, sub_peak, cfg.band_db_down)
    e_low, e_high = _energy_band_edges(sub_freqs, sub_power, sub_peak, cfg.energy_fraction)

    # Recommended edges: widest of the two measured bands, plus a margin.
    meas_low = min(band_low, e_low)
    meas_high = max(band_high, e_high)
    low_margin = max(cfg.min_margin_hz, cfg.margin_frac * meas_low)
    high_margin = max(cfg.min_margin_hz, cfg.margin_frac * meas_high)
    rec_low = _round_to(max(cfg.wind_floor_hz, meas_low - low_margin), cfg.round_to_hz)
    rec_high = _round_to(min(cfg.nyquist * 0.99, meas_high + high_margin), cfg.round_to_hz)
    if rec_high <= rec_low:  # degenerate guard
        rec_high = _round_to(min(cfg.nyquist * 0.99, rec_low + 2 * high_margin), cfg.round_to_hz)

    # In-band SNR: mean in-band power vs. above-wind out-of-band floor.
    in_mask = (freqs >= meas_low) & (freqs <= meas_high)
    out_mask = search & ~in_mask
    in_power = float(power[in_mask].mean()) if in_mask.any() else float(power[peak_idx])
    out_power = float(np.median(power[out_mask])) if out_mask.any() else 1e-12
    in_band_snr_db = float(10.0 * np.log10(max(in_power, 1e-12) / max(out_power, 1e-12)))

    rec_k = _recommend_threshold_k(in_band_snr_db, cfg.threshold_k_bounds)

    spectrogram_db = librosa.amplitude_to_db(magnitude, ref=np.max)
    mean_power_db = 10.0 * np.log10(power / (power.max() or 1e-12) + 1e-12)

    return CalibrationResult(
        sample_rate=cfg.sample_rate,
        duration_s=float(len(y) / cfg.sample_rate),
        peak_freq_hz=peak_freq,
        band_low_hz=band_low,
        band_high_hz=band_high,
        energy_band_low_hz=e_low,
        energy_band_high_hz=e_high,
        recommended_lowcut_hz=rec_low,
        recommended_highcut_hz=rec_high,
        recommended_threshold_k=rec_k,
        in_band_snr_db=in_band_snr_db,
        freqs=freqs,
        mean_power_db=mean_power_db,
        spectrogram_db=spectrogram_db,
        times=times,
    )


def format_summary(result: CalibrationResult, source: str | Path) -> str:
    """Human-readable calibration report."""
    lines = [
        "Calibration summary",
        "===================",
        f"reference        : {source}",
        f"duration         : {result.duration_s:.1f} s @ {result.sample_rate} Hz",
        f"peak frequency   : {result.peak_freq_hz:.0f} Hz",
        f"band (-dB)       : {result.band_low_hz:.0f}–{result.band_high_hz:.0f} Hz",
        f"band (energy)    : {result.energy_band_low_hz:.0f}–"
        f"{result.energy_band_high_hz:.0f} Hz",
        f"in-band SNR      : {result.in_band_snr_db:.1f} dB",
        "",
        "Recommended DetectionConfig",
        "---------------------------",
        f"  lowcut_hz    = {result.recommended_lowcut_hz:.0f}",
        f"  highcut_hz   = {result.recommended_highcut_hz:.0f}",
        f"  threshold_k  = {result.recommended_threshold_k:.2f}",
    ]
    return "\n".join(lines)


def save_calibration_plot(
    result: CalibrationResult,
    out_path: str | Path,
    title: str = "Reference calibration",
) -> Path:
    """Render the reference spectrogram + mean power spectrum with the band marked."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    fig, (ax_spec, ax_spectrum) = plt.subplots(
        1, 2, figsize=(14, 6), gridspec_kw={"width_ratios": [3, 1]}
    )

    y_ceiling = min(result.recommended_highcut_hz * 1.8, result.freqs[-1])
    extent = [result.times[0], result.times[-1], result.freqs[0], result.freqs[-1]]
    ax_spec.imshow(
        result.spectrogram_db,
        aspect="auto",
        origin="lower",
        extent=extent,
        cmap="magma",
        vmin=-80,
        vmax=0,
    )
    for edge, label in (
        (result.recommended_lowcut_hz, "lowcut"),
        (result.recommended_highcut_hz, "highcut"),
    ):
        ax_spec.axhline(edge, color="cyan", ls="--", lw=1.0, alpha=0.8)
    ax_spec.axhline(result.peak_freq_hz, color="lime", ls="-", lw=1.0, alpha=0.7)
    ax_spec.set_ylim(0, y_ceiling)
    ax_spec.set_xlabel("Time (s)")
    ax_spec.set_ylabel("Frequency (Hz)")
    ax_spec.set_title(title)

    # Mean power spectrum, plotted with frequency on the vertical axis to align
    # visually with the spectrogram.
    ax_spectrum.plot(result.mean_power_db, result.freqs, color="steelblue", lw=1.0)
    ax_spectrum.axhspan(
        result.recommended_lowcut_hz,
        result.recommended_highcut_hz,
        color="cyan",
        alpha=0.12,
        label="recommended band",
    )
    ax_spectrum.axhline(result.peak_freq_hz, color="lime", ls="-", lw=1.0,
                        label=f"peak {result.peak_freq_hz:.0f} Hz")
    ax_spectrum.set_ylim(0, y_ceiling)
    ax_spectrum.set_xlabel("Mean power (dB)")
    ax_spectrum.set_title("Mean power spectrum")
    ax_spectrum.legend(loc="upper left", fontsize=8)

    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)
    return out_path


def write_calibration_json(
    result: CalibrationResult, cfg: CalibrationConfig, out_path: str | Path
) -> Path:
    """Write the recommended config (+ measurements) to a JSON file."""
    import json

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = result.to_dict()
    payload["calibration"] = {
        "n_fft": cfg.n_fft,
        "hop_length": cfg.hop_length,
        "wind_floor_hz": cfg.wind_floor_hz,
        "band_db_down": cfg.band_db_down,
        "energy_fraction": cfg.energy_fraction,
    }
    # ``config`` mirrors DetectionConfig field names so detect.py can load it.
    payload["config"] = {
        "lowcut_hz": round(result.recommended_lowcut_hz, 1),
        "highcut_hz": round(result.recommended_highcut_hz, 1),
        "threshold_k": round(result.recommended_threshold_k, 2),
    }
    out_path.write_text(json.dumps(payload, indent=2) + "\n")
    return out_path
