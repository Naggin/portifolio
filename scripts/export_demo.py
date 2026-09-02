"""Generate a multi-file demo report and copy it into the Vite public folder.

Creates several synthetic recordings with recorder-style filenames at different
hours and months, runs the detection pipeline, and writes:

  web/public/demo/resultado.json
  web/public/demo/*.png
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from bioacoustics.config import DetectionConfig  # noqa: E402
from bioacoustics.pipeline import process_file  # noqa: E402
from bioacoustics.report import write_json_report  # noqa: E402
from bioacoustics.visualization import save_file_spectrograms  # noqa: E402
from generate_sample import synthesize  # noqa: E402

DEMO_DIR = ROOT / "web" / "public" / "demo"

# Field-season filenames: dusk/night chorus across a few months.
RECORDINGS = [
    ("R20240914-183012.WAV", 11),
    ("R20241003-191145.WAV", 22),
    ("R20241011-180923.WAV", 42),
    ("R20241011-210430.WAV", 7),
    ("R20241012-001205.WAV", 19),
    ("R20241102-193355.WAV", 33),
    ("R20241115-221018.WAV", 55),
    ("R20241208-184500.WAV", 3),
]


def main() -> None:
    cfg = DetectionConfig()
    DEMO_DIR.mkdir(parents=True, exist_ok=True)

    staging = ROOT / "output" / "demo_staging"
    staging.mkdir(parents=True, exist_ok=True)

    results = []
    for name, seed in RECORDINGS:
        wav = staging / name
        audio = synthesize(sr=cfg.sample_rate, duration_s=30.0, seed=seed)
        sf.write(str(wav), audio, cfg.sample_rate, subtype="PCM_16")
        print(f"Processing {name} ...")
        result = process_file(wav, cfg)
        results.append(result)
        written = save_file_spectrograms(
            wav,
            result.detection.events,
            result.detection.duration_s,
            cfg,
            staging,
            title=f"{name} — cantos detectados",
            result=result.detection,
            write_zoom=False,
        )
        shutil.copy2(written[0].path, DEMO_DIR / written[0].path.name)
        print(f"  {result.detection.n_events} calls, max {result.detection.max_simultaneous} simultaneous")

    json_path = DEMO_DIR / "resultado.json"
    write_json_report(results, json_path, cfg)
    shutil.copy2(json_path, ROOT / "output" / "resultado.json")
    print(f"Wrote {json_path}")


if __name__ == "__main__":
    main()
