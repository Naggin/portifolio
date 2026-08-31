"""Core acoustic-event detection.

Pipeline for a single audio buffer:
  1. Band-pass filter (drop wind / low-frequency rumble).
  2. Optional spectral noise reduction.
  3. Numeric spectrogram (STFT magnitude) restricted to the species band.
  4. Per-frame band energy -> adaptive threshold -> energy peaks with timestamps.
  5. Group nearby peaks into call events.
  6. Estimate simultaneous callers by looking at events that overlap in time
     but differ in dominant frequency.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.signal import butter, find_peaks, sosfiltfilt

from .config import DetectionConfig


@dataclass
class CallEvent:
    start_s: float
    end_s: float
    peak_time_s: float
    peak_freq_hz: float
    energy: float
    n_callers: int = 1  # simultaneous individuals estimated within this event.

    @property
    def duration_s(self) -> float:
        return self.end_s - self.start_s


@dataclass
class DetectionResult:
    events: list[CallEvent]
    max_simultaneous: int
    duration_s: float
    # Intermediate arrays kept for visualization / debugging.
    spectrogram_db: np.ndarray
    freqs: np.ndarray
    times: np.ndarray
    band_energy: np.ndarray
    threshold: float

    @property
    def n_events(self) -> int:
        return len(self.events)


def bandpass_filter(y: np.ndarray, cfg: DetectionConfig) -> np.ndarray:
    """Apply a zero-phase Butterworth band-pass filter.

    A short cosine taper is applied to the signal edges first: an abrupt
    boundary (e.g. wind present at t=0) makes ``sosfiltfilt`` ring inside the
    pass-band and produces spurious energy at the very start/end of the file.
    """
    y = _taper_edges(y, cfg)
    high = min(cfg.highcut_hz, cfg.nyquist * 0.99)
    sos = butter(
        cfg.filter_order,
        [cfg.lowcut_hz, high],
        btype="band",
        fs=cfg.sample_rate,
        output="sos",
    )
    return sosfiltfilt(sos, y).astype(np.float32)


def _taper_edges(y: np.ndarray, cfg: DetectionConfig, taper_s: float = 0.05) -> np.ndarray:
    """Fade the first/last ``taper_s`` seconds to zero to tame filter transients."""
    n = int(taper_s * cfg.sample_rate)
    if n <= 0 or 2 * n >= len(y):
        return y
    ramp = 0.5 * (1 - np.cos(np.linspace(0, np.pi, n)))
    out = y.copy()
    out[:n] *= ramp
    out[-n:] *= ramp[::-1]
    return out


def reduce_noise(y: np.ndarray, cfg: DetectionConfig) -> np.ndarray:
    """Spectral noise reduction; degrades gracefully if the lib is missing."""
    if not cfg.use_noise_reduction:
        return y
    try:
        import noisereduce as nr
    except Exception:  # pragma: no cover - optional dependency
        return y
    reduced = nr.reduce_noise(
        y=y,
        sr=cfg.sample_rate,
        prop_decrease=cfg.noise_reduce_prop_decrease,
    )
    return reduced.astype(np.float32)


def compute_spectrogram(
    y: np.ndarray, cfg: DetectionConfig
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return (magnitude, freqs, times) from the STFT of ``y``."""
    import librosa

    stft = librosa.stft(y, n_fft=cfg.n_fft, hop_length=cfg.hop_length)
    magnitude = np.abs(stft)
    freqs = librosa.fft_frequencies(sr=cfg.sample_rate, n_fft=cfg.n_fft)
    times = librosa.frames_to_time(
        np.arange(magnitude.shape[1]), sr=cfg.sample_rate, hop_length=cfg.hop_length
    )
    return magnitude, freqs, times


def _band_mask(freqs: np.ndarray, cfg: DetectionConfig) -> np.ndarray:
    return (freqs >= cfg.lowcut_hz) & (freqs <= cfg.highcut_hz)


def detect_events(
    magnitude: np.ndarray,
    freqs: np.ndarray,
    times: np.ndarray,
    cfg: DetectionConfig,
) -> tuple[list[CallEvent], np.ndarray, float]:
    """Detect call events from a spectrogram magnitude matrix.

    Returns (events, band_energy_per_frame, threshold).
    """
    band = _band_mask(freqs, cfg)
    band_mag = magnitude[band, :]
    band_freqs = freqs[band]

    # Energy per frame within the species band.
    band_energy = band_mag.sum(axis=0)

    # Adaptive threshold: median + k * MAD (robust to sustained noise floors).
    median = float(np.median(band_energy))
    mad = float(np.median(np.abs(band_energy - median))) or 1e-9
    threshold = median + cfg.threshold_k * mad

    if len(times) > 1:
        frame_dt = float(np.median(np.diff(times)))
    else:
        frame_dt = cfg.hop_length / cfg.sample_rate

    # Contiguous runs of frames above threshold are candidate call segments.
    above = band_energy >= threshold
    # Exclude the filter settling margin at both edges from detection.
    above[times < (times[0] + cfg.edge_guard_s)] = False
    above[times > (times[-1] - cfg.edge_guard_s)] = False
    segments = _contiguous_runs(above)
    if not segments:
        return [], band_energy, threshold

    # Merge segments separated by a gap shorter than event_merge_gap_s.
    merged: list[tuple[int, int]] = [segments[0]]
    for start, end in segments[1:]:
        prev_start, prev_end = merged[-1]
        if (times[start] - times[prev_end]) <= cfg.event_merge_gap_s:
            merged[-1] = (prev_start, end)
        else:
            merged.append((start, end))

    events: list[CallEvent] = []
    for start, end in merged:
        # Duration measured across frames (single-frame runs get one frame_dt).
        duration = (end - start + 1) * frame_dt
        if duration < cfg.min_event_duration_s:
            continue
        events.append(
            _build_event(start, end, frame_dt, band_mag, band_freqs, times, band_energy, cfg)
        )
    return events, band_energy, threshold


def _contiguous_runs(mask: np.ndarray) -> list[tuple[int, int]]:
    """Return (start_idx, end_idx) inclusive ranges where ``mask`` is True."""
    runs: list[tuple[int, int]] = []
    idx = np.flatnonzero(mask)
    if idx.size == 0:
        return runs
    breaks = np.flatnonzero(np.diff(idx) > 1)
    starts = np.concatenate(([idx[0]], idx[breaks + 1]))
    ends = np.concatenate((idx[breaks], [idx[-1]]))
    return list(zip(starts.tolist(), ends.tolist()))


def _count_callers_in_frame(
    column: np.ndarray, band_freqs: np.ndarray, cfg: DetectionConfig
) -> int:
    """Count distinct spectral peaks (individuals) in one spectrogram column."""
    if column.max() <= 0:
        return 0
    bin_width = float(band_freqs[1] - band_freqs[0]) if len(band_freqs) > 1 else 1.0
    distance = max(1, int(round(cfg.freq_separation_hz / bin_width)))
    peaks, _ = find_peaks(
        column, height=column.max() * cfg.caller_rel_height, distance=distance
    )
    return int(len(peaks))


def _build_event(
    start: int,
    end: int,
    frame_dt: float,
    band_mag: np.ndarray,
    band_freqs: np.ndarray,
    times: np.ndarray,
    band_energy: np.ndarray,
    cfg: DetectionConfig,
) -> CallEvent:
    peak_frame = start + int(np.argmax(band_energy[start : end + 1]))
    dominant_bin = int(np.argmax(band_mag[:, peak_frame]))
    # Simultaneous callers: max distinct spectral peaks across the event frames.
    n_callers = max(
        (_count_callers_in_frame(band_mag[:, f], band_freqs, cfg)
         for f in range(start, end + 1)),
        default=1,
    )
    return CallEvent(
        start_s=float(times[start]),
        end_s=float(times[end] + frame_dt),
        peak_time_s=float(times[peak_frame]),
        peak_freq_hz=float(band_freqs[dominant_bin]),
        energy=float(band_energy[peak_frame]),
        n_callers=max(1, n_callers),
    )


def count_max_simultaneous(events: list[CallEvent], cfg: DetectionConfig) -> int:
    """Maximum number of individuals estimated to call at the same time.

    Combines two signals: distinct spectral peaks within a single event
    (two callers overlapping at different pitches) and separate events that
    overlap in time at sufficiently different dominant frequencies.
    """
    if not events:
        return 0

    max_count = max(e.n_callers for e in events)

    # Also account for distinct events that overlap in time.
    for probe in events:
        t = probe.peak_time_s
        active = [e for e in events if e.start_s <= t <= e.end_s]
        active.sort(key=lambda e: e.peak_freq_hz)
        clusters = 0
        last_freq = None
        for e in active:
            if last_freq is None or (e.peak_freq_hz - last_freq) >= cfg.freq_separation_hz:
                clusters += 1
                last_freq = e.peak_freq_hz
        max_count = max(max_count, clusters)
    return max_count


def run_detection(y: np.ndarray, cfg: DetectionConfig) -> DetectionResult:
    """Run the full detection pipeline on a mono audio buffer."""
    filtered = bandpass_filter(y, cfg)
    denoised = reduce_noise(filtered, cfg)
    magnitude, freqs, times = compute_spectrogram(denoised, cfg)
    events, band_energy, threshold = detect_events(magnitude, freqs, times, cfg)
    max_simultaneous = count_max_simultaneous(events, cfg)

    # dB spectrogram (species band) for visualization.
    import librosa

    spectrogram_db = librosa.amplitude_to_db(magnitude, ref=np.max)

    duration_s = float(len(y) / cfg.sample_rate)
    return DetectionResult(
        events=events,
        max_simultaneous=max_simultaneous,
        duration_s=duration_s,
        spectrogram_db=spectrogram_db,
        freqs=freqs,
        times=times,
        band_energy=band_energy,
        threshold=threshold,
    )
