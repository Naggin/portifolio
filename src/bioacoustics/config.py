"""Detection parameters for the acoustic pipeline.

Defaults target the calling range of small Atlantic-forest hylids
(Sphaenorhynchus caramaschii). They are meant to be tuned in Phase 2 using a
clean reference recording of the species.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class DetectionConfig:
    # --- Loading ---
    sample_rate: int = 22_050  # Hz; downsampled on load to keep processing light.

    # --- Band-pass filter (removes wind, which is low-frequency energy) ---
    lowcut_hz: float = 1_500.0
    highcut_hz: float = 4_000.0
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
    # Within a call, two spectral peaks count as distinct individuals only if
    # they differ by at least this many Hz (rough proxy for two callers).
    freq_separation_hz: float = 250.0
    # A spectral peak must reach this fraction of the frame's strongest peak to
    # count as a distinct caller (rejects side-lobes / weak harmonics).
    caller_rel_height: float = 0.3

    # --- Edge handling ---
    # Zero-phase (forward-backward) filtering rings at the signal boundaries for
    # roughly this long. Frames within this margin of the file start/end are
    # excluded from detection. Negligible for hour-long files, and chunked
    # processing (Phase 4) overlaps chunks so nothing real is lost.
    edge_guard_s: float = 1.5

    @property
    def nyquist(self) -> float:
        return self.sample_rate / 2.0
