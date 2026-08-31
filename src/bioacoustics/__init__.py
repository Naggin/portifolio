"""Automatic detection and counting of Sphaenorhynchus caramaschii vocalizations.

This package implements the core signal-processing pipeline described in the
project roadmap: load an audio recording, filter out low-frequency wind noise,
compute a numeric spectrogram, detect acoustic events (calls) with timestamps,
estimate how many individuals vocalize simultaneously, and export a report.
"""

from .config import DetectionConfig
from .pipeline import PipelineResult, process_file

__all__ = ["DetectionConfig", "PipelineResult", "process_file"]

__version__ = "0.1.0"
