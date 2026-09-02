"""Detection parameters for the acoustic pipeline.

Calibrated in Phase 2 from the clean species reference
``Áudio base/CEAES 2.m4a`` (29 s, peak energy ~2.89 kHz, voiced frames
roughly 2.63–3.09 kHz). Field recordings are hour-scale WAVs/MP3s with wind;
the band is kept tight so low-frequency rumble never becomes a call.
"""

from __future__ import annotations

from dataclasses import dataclass


# Shared by the CLI and the HTTP API.
AUDIO_EXTENSIONS = (".wav", ".flac", ".ogg", ".mp3", ".m4a")


@dataclass
class DetectionConfig:
    # --- Loading ---
    sample_rate: int = 22_050  # Hz; downsampled on load to keep processing light.

    # --- Band-pass filter (removes wind, which is low-frequency energy) ---
    # Species advertisement energy on CEAES 2 sits ~2.8–3.0 kHz (p10–p90).
    lowcut_hz: float = 2_600.0
    highcut_hz: float = 3_200.0
    filter_order: int = 4

    # --- Spectrogram (STFT) ---
    n_fft: int = 2_048
    hop_length: int = 512

    # --- Noise reduction ---
    use_noise_reduction: bool = True
    noise_reduce_prop_decrease: float = 0.9

    # --- Peak / event detection ---
    # Energy threshold expressed as (median + k * MAD) of the band energy.
    threshold_k: float = 6.0
    # Minimum gap (seconds) between two energy peaks to count as separate onsets.
    min_peak_distance_s: float = 0.15
    # Peaks closer than this (seconds) are grouped into a single call event.
    event_merge_gap_s: float = 0.4
    # Minimum duration (seconds) for a group of peaks to count as a call.
    min_event_duration_s: float = 0.05

    # --- Simultaneity / individual counting ---
    # One frog of this species has a ~200 Hz-wide ridge around 2.9 kHz. Peaks
    # closer than this are treated as the same individual (the uncalibrated
    # 250 Hz / 0.3 height settings counted 7 "callers" on a single-species clip).
    freq_separation_hz: float = 400.0
    # A spectral peak must reach this fraction of the frame's strongest peak to
    # count as a distinct caller (rejects side-lobes / weak harmonics).
    caller_rel_height: float = 0.55

    # --- Edge handling ---
    # Zero-phase (forward-backward) filtering rings at the signal boundaries for
    # roughly this long. Frames within this margin of each chunk's start/end are
    # excluded. Chunks overlap by ``2 * edge_guard_s`` so nothing real is lost.
    edge_guard_s: float = 1.5

    # --- Long files (field WAVs/MP3s of 1–6 h) ---
    # Process in overlapping windows instead of loading the whole recording.
    chunk_duration_s: float = 60.0
    chunk_overlap_s: float = 3.0  # 2 * edge_guard_s
    # PNG length for long files: densest window with peaks, not the first 60 s.
    spectrogram_preview_s: float = 60.0

    @property
    def nyquist(self) -> float:
        return self.sample_rate / 2.0
