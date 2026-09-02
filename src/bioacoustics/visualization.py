"""Spectrogram rendering for human validation (not used for counting)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import matplotlib
import numpy as np

matplotlib.use("Agg")  # headless rendering
import matplotlib.pyplot as plt  # noqa: E402
import librosa  # noqa: E402

from .audio_io import audio_duration_s, load_audio_segment  # noqa: E402
from .config import DetectionConfig  # noqa: E402
from .detection import (  # noqa: E402
    CallEvent,
    DetectionResult,
    bandpass_filter,
    compute_spectrogram,
    reduce_noise,
)

ZOOM_WINDOW_S = 8.0
# Context around one table-row event so the PNG is not a 0.09 s sliver.
EVENT_CONTEXT_PAD_S = 1.25
EVENT_MAX_WINDOW_S = 8.0

EventLike = CallEvent | dict[str, Any]


@dataclass(frozen=True)
class SpectrogramOutput:
    """One PNG written for human validation."""

    path: Path
    t0: float
    duration_s: float
    n_marked: int
    kind: str  # "full" | "window" | "zoom" | "event"


def densest_window_start(
    events: Sequence[EventLike],
    window_s: float,
    duration_s: float | None = None,
) -> float:
    """Start time of the ``window_s`` interval that contains the most peaks.

    Ties keep the earliest cluster. When ``duration_s`` is given, the start is
    clamped so the window stays inside the recording.
    """
    times = sorted(_peak_time(ev) for ev in events)
    if not times or window_s <= 0:
        return 0.0
    best_i = 0
    best_n = 0
    j = 0
    n = len(times)
    for i, t in enumerate(times):
        while j < n and times[j] < t + window_s:
            j += 1
        count = j - i
        if count > best_n:
            best_n = count
            best_i = i
    t0 = float(times[best_i])
    if duration_s is not None and duration_s > window_s:
        t0 = min(t0, float(duration_s) - window_s)
    return max(0.0, t0)


def loudest_event_in_window(
    events: Sequence[EventLike],
    t0: float,
    t1: float,
) -> EventLike | None:
    """Event with the highest band energy whose peak falls in ``[t0, t1]``."""
    visible = [ev for ev in events if t0 <= _peak_time(ev) <= t1]
    if not visible:
        return None
    return max(visible, key=_energy)


def save_spectrogram(
    result: DetectionResult,
    cfg: DetectionConfig,
    out_path: str | Path,
    title: str = "Spectrogram with detected calls",
) -> Path:
    """Render ``result.spectrogram_db`` with detected call peaks marked.

    On chunked long files this array is only the first analysis window.
    Prefer :func:`save_file_spectrograms` / :func:`save_spectrogram_window`
    so the PNG covers the peaks, not t=0.
    """
    spec_times = result.preview_times if result.preview_times is not None else result.times
    t0, t1 = float(spec_times[0]), float(spec_times[-1])
    mask = (result.times >= t0) & (result.times <= t1)
    if not np.any(mask):
        mask = np.ones(len(result.times), dtype=bool)
    return _draw_spectrogram(
        spectrogram_db=result.spectrogram_db,
        freqs=result.freqs,
        spec_times=spec_times,
        band_energy=result.band_energy[mask],
        energy_times=result.times[mask],
        events=result.events,
        cfg=cfg,
        out_path=out_path,
        title=title,
        threshold=float(result.threshold),
    )


def save_spectrogram_window(
    path: str | Path,
    events: Sequence[EventLike],
    t0: float,
    duration_s: float,
    cfg: DetectionConfig,
    out_path: str | Path,
    title: str,
) -> SpectrogramOutput:
    """STFT of ``[t0, t0+duration_s)`` with batch events marked (no re-count).

    Loads that slice with :func:`load_audio_segment`, applies the same
    band-pass / denoise as the detector so the image matches what was
    counted, then overlays the *existing* event list as lime markers.
    """
    t0 = max(0.0, float(t0))
    duration_s = max(0.05, float(duration_s))
    y, _sr = load_audio_segment(path, cfg.sample_rate, offset_s=t0, duration_s=duration_s)
    if y.size == 0:
        raise ValueError(f"empty audio segment at t={t0:.3f}s in {path}")

    filtered = bandpass_filter(y, cfg)
    denoised = reduce_noise(filtered, cfg)
    magnitude, freqs, rel_times = compute_spectrogram(denoised, cfg)
    spec_times = rel_times + t0
    spectrogram_db = librosa.amplitude_to_db(magnitude, ref=np.max)

    band = (freqs >= cfg.lowcut_hz) & (freqs <= cfg.highcut_hz)
    band_energy = magnitude[band, :].sum(axis=0) if np.any(band) else magnitude.sum(axis=0)
    median = float(np.median(band_energy))
    mad = float(np.median(np.abs(band_energy - median))) or 1e-9
    threshold = median + cfg.threshold_k * mad

    actual_duration = float(len(y) / cfg.sample_rate)
    t1 = t0 + actual_duration
    n_marked = sum(1 for ev in events if t0 <= _peak_time(ev) <= t1)

    png = _draw_spectrogram(
        spectrogram_db=spectrogram_db,
        freqs=freqs,
        spec_times=spec_times,
        band_energy=band_energy,
        energy_times=spec_times,
        events=events,
        cfg=cfg,
        out_path=out_path,
        title=title,
        threshold=threshold,
        xlabel="Tempo (s)",
        ylabel="Frequência (Hz)",
        energy_label="Energia da banda",
    )
    return SpectrogramOutput(
        path=png,
        t0=t0,
        duration_s=actual_duration,
        n_marked=n_marked,
        kind="window",
    )


def event_context_window(
    start_s: float,
    end_s: float,
    duration_s: float,
    *,
    pad_s: float = EVENT_CONTEXT_PAD_S,
    max_window_s: float = EVENT_MAX_WINDOW_S,
    peak_time_s: float | None = None,
) -> tuple[float, float]:
    """``(t0, duration)`` with padding around the event, clamped to the file.

    Times are file-absolute. A typical 0.09 s call becomes a few seconds of
    context; a pathological long span is capped around the peak.
    """
    start_s = max(0.0, float(start_s))
    end_s = max(start_s, float(end_s))
    duration_s = max(0.0, float(duration_s))
    pad_s = max(0.0, float(pad_s))
    t0 = max(0.0, start_s - pad_s)
    t1 = min(duration_s, end_s + pad_s) if duration_s > 0 else end_s + pad_s
    if t1 <= t0:
        t1 = t0 + max(0.05, pad_s * 2.0)
        if duration_s > 0:
            t1 = min(duration_s, t1)
            t0 = max(0.0, min(t0, t1 - 0.05))
    span = t1 - t0
    max_window_s = max(0.05, float(max_window_s))
    if span > max_window_s:
        center = float(peak_time_s) if peak_time_s is not None else 0.5 * (start_s + end_s)
        half = max_window_s / 2.0
        t0 = max(0.0, center - half)
        t1 = t0 + max_window_s
        if duration_s > 0 and t1 > duration_s:
            t1 = duration_s
            t0 = max(0.0, t1 - max_window_s)
    return t0, max(0.05, t1 - t0)


def event_spectrogram_title(
    filename: str,
    event_n: int | None,
    peak_time_s: float,
    peak_freq_hz: float,
    n_callers: int | None,
) -> str:
    """Caption for one table row. ``n_callers`` is simultaneous peaks, not an ID."""
    bits = [filename]
    if event_n is not None:
        bits.append(f"evento {int(event_n)}")
    bits.append(f"pico {float(peak_time_s):.3f} s, {float(peak_freq_hz):.0f} Hz")
    title = " — ".join(bits)
    if n_callers is not None:
        title += f"\ncantores simultâneos estimados: {int(n_callers)}"
    return title


def save_event_spectrogram(
    path: str | Path,
    event: EventLike,
    cfg: DetectionConfig,
    out_path: str | Path,
    *,
    filename: str | None = None,
    event_n: int | None = None,
    duration_s: float | None = None,
    pad_s: float = EVENT_CONTEXT_PAD_S,
) -> SpectrogramOutput:
    """Render one already-detected event with context. Does not re-run detection.

    Marks the given ``peak_time_s`` / ``peak_freq_hz`` and the call span; the
    x-axis stays in file-absolute seconds (same numbers as the Events table).
    """
    start_s, end_s = _span(event)
    peak_t = _peak_time(event)
    peak_f = _peak_freq(event)
    if duration_s is None:
        duration_s = audio_duration_s(path)
    t0, win = event_context_window(
        start_s, end_s, float(duration_s), pad_s=pad_s, peak_time_s=peak_t
    )
    name = filename or Path(path).name
    n_callers = _n_callers(event)
    title = event_spectrogram_title(name, event_n, peak_t, peak_f, n_callers)
    written = save_spectrogram_window(
        path, [event], t0, win, cfg, out_path, title
    )
    return SpectrogramOutput(
        path=written.path,
        t0=written.t0,
        duration_s=written.duration_s,
        n_marked=written.n_marked,
        kind="event",
    )


def save_file_spectrograms(
    path: str | Path,
    events: Sequence[EventLike],
    duration_s: float,
    cfg: DetectionConfig,
    out_dir: str | Path,
    *,
    title: str | None = None,
    result: DetectionResult | None = None,
    write_zoom: bool = True,
) -> list[SpectrogramOutput]:
    """Write ``{stem}_spectrogram.png`` on the densest peak window (or the whole file).

    Files shorter than ``cfg.spectrogram_preview_s`` keep a full-file PNG.
    Longer files use the window that actually contains peaks, not the first
    60 s. Optionally also writes ``{stem}_pico_{t:.0f}s.png`` (~8 s) around
    the loudest event in that window. The dashboard still reads the main PNG.
    """
    path = Path(path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = path.stem
    preview_s = float(cfg.spectrogram_preview_s)
    duration_s = float(duration_s)
    main_png = out_dir / f"{stem}_spectrogram.png"
    name = path.name
    written: list[SpectrogramOutput] = []

    if duration_s <= preview_s:
        heading = title or f"{name} — picos de vocalização"
        if result is not None:
            save_spectrogram(result, cfg, main_png, title=heading)
            n_marked = sum(1 for ev in events if 0.0 <= _peak_time(ev) <= duration_s)
            main = SpectrogramOutput(
                path=main_png,
                t0=0.0,
                duration_s=duration_s,
                n_marked=n_marked,
                kind="full",
            )
        else:
            main = save_spectrogram_window(
                path, events, 0.0, duration_s, cfg, main_png, heading
            )
            main = SpectrogramOutput(
                path=main.path,
                t0=main.t0,
                duration_s=main.duration_s,
                n_marked=main.n_marked,
                kind="full",
            )
        t0, t1 = main.t0, main.t0 + main.duration_s
        written.append(main)
    else:
        t0 = densest_window_start(events, preview_s, duration_s)
        win = min(preview_s, max(0.05, duration_s - t0))
        t1 = t0 + win
        heading = title or (
            f"{name} — {_fmt_mmss(t0)}–{_fmt_mmss(t1)} — picos de vocalização"
        )
        main = save_spectrogram_window(path, events, t0, win, cfg, main_png, heading)
        written.append(main)

    if write_zoom:
        loudest = loudest_event_in_window(events, t0, t1)
        if loudest is not None:
            peak = _peak_time(loudest)
            zoom = min(ZOOM_WINDOW_S, duration_s)
            z0 = max(0.0, peak - zoom / 2.0)
            if z0 + zoom > duration_s:
                z0 = max(0.0, duration_s - zoom)
            freq = _peak_freq(loudest)
            zoom_title = (
                f"{name} — zoom {zoom:.0f} s no pico mais forte "
                f"(~{peak:.0f} s, {freq / 1000:.2f} kHz)"
            )
            zoom_png = out_dir / f"{stem}_pico_{peak:.0f}s.png"
            zoom_out = save_spectrogram_window(
                path, events, z0, zoom, cfg, zoom_png, zoom_title
            )
            written.append(
                SpectrogramOutput(
                    path=zoom_out.path,
                    t0=zoom_out.t0,
                    duration_s=zoom_out.duration_s,
                    n_marked=zoom_out.n_marked,
                    kind="zoom",
                )
            )
    return written


def _peak_time(ev: EventLike) -> float:
    return float(ev["peak_time_s"] if isinstance(ev, dict) else ev.peak_time_s)


def _peak_freq(ev: EventLike) -> float:
    return float(ev["peak_freq_hz"] if isinstance(ev, dict) else ev.peak_freq_hz)


def _energy(ev: EventLike) -> float:
    return float(ev["energy"] if isinstance(ev, dict) else ev.energy)


def _n_callers(ev: EventLike) -> int:
    if isinstance(ev, dict):
        raw = ev.get("n_callers", 1)
    else:
        raw = getattr(ev, "n_callers", 1)
    try:
        return max(1, int(raw))
    except (TypeError, ValueError):
        return 1


def _span(ev: EventLike) -> tuple[float, float]:
    if isinstance(ev, dict):
        return float(ev["start_s"]), float(ev["end_s"])
    return float(ev.start_s), float(ev.end_s)


def _fmt_mmss(t: float) -> str:
    t = max(0.0, float(t))
    m, s = divmod(int(round(t)), 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _draw_spectrogram(
    *,
    spectrogram_db: np.ndarray,
    freqs: np.ndarray,
    spec_times: np.ndarray,
    band_energy: np.ndarray,
    energy_times: np.ndarray,
    events: Sequence[EventLike],
    cfg: DetectionConfig,
    out_path: str | Path,
    title: str,
    threshold: float,
    xlabel: str = "Time (s)",
    ylabel: str = "Frequency (Hz)",
    energy_label: str = "Energy",
) -> Path:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    fig, (ax_spec, ax_energy) = plt.subplots(
        2, 1, figsize=(12, 6.5), sharex=True, gridspec_kw={"height_ratios": [3, 1]}
    )

    t0, t1 = float(spec_times[0]), float(spec_times[-1])
    extent = [t0, t1, float(freqs[0]), float(freqs[-1])]
    ax_spec.imshow(
        spectrogram_db,
        aspect="auto",
        origin="lower",
        extent=extent,
        cmap="magma",
        vmin=-80,
        vmax=0,
    )
    ax_spec.axhline(cfg.lowcut_hz, color="cyan", ls="--", lw=0.8, alpha=0.7)
    ax_spec.axhline(cfg.highcut_hz, color="cyan", ls="--", lw=0.8, alpha=0.7)
    ax_spec.set_ylim(0, min(cfg.highcut_hz * 1.5, float(freqs[-1])))
    ax_spec.set_ylabel(ylabel)
    ax_spec.set_title(title)

    visible = [ev for ev in events if t0 <= _peak_time(ev) <= t1]
    for ev in visible:
        peak_t = _peak_time(ev)
        ax_spec.axvline(peak_t, color="lime", lw=0.8, alpha=0.75)
        ax_spec.plot(
            peak_t,
            _peak_freq(ev),
            "o",
            color="lime",
            ms=6,
            mew=1.2,
            markerfacecolor="none",
        )
        start_s, end_s = _span(ev)
        ax_spec.axvspan(start_s, end_s, color="lime", alpha=0.08)

    ax_energy.plot(
        energy_times, band_energy, color="steelblue", lw=0.8, label=energy_label
    )
    ax_energy.axhline(threshold, color="red", ls="--", lw=1.0, label="Limiar" if xlabel.startswith("Tempo") else "Threshold")
    for ev in visible:
        ax_energy.axvline(_peak_time(ev), color="lime", lw=0.6, alpha=0.6)
    ax_energy.set_xlabel(xlabel)
    ax_energy.set_ylabel(energy_label)
    ax_energy.legend(loc="upper right", fontsize=8)

    fig.tight_layout()
    fig.savefig(out_path, dpi=110, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    _optimize_png(out_path)
    return out_path


def _optimize_png(path: Path) -> None:
    """Keep validation PNGs at a few hundred KB when possible."""
    try:
        from PIL import Image
    except Exception:  # pragma: no cover - pillow ships with matplotlib extras
        return
    with Image.open(path) as im:
        im = im.convert("RGB")
        im.save(path, format="PNG", optimize=True)
