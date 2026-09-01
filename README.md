# Bioacústica — Contagem Automática de *Sphaenorhynchus caramaschii*

Automated detection and counting of *Sphaenorhynchus caramaschii* (perereca-de-banhado)
vocalizations in field recordings, replacing hundreds of hours of manual listening.

This repository implements **Phase 0 + Phase 1** of the project roadmap: the core
signal-processing pipeline that takes one audio file and

1. loads it with `librosa`,
2. band-pass filters it to the species' calling range (removing low-frequency wind),
3. applies spectral noise reduction,
4. computes the spectrogram **as a numeric matrix** (not an image),
5. detects each call as an acoustic event with an exact timestamp,
6. estimates how many individuals call **simultaneously** (distinct spectral peaks),
7. renders a spectrogram PNG for human validation, and
8. exports an `.xlsx` report with per-event detail and hourly/monthly charts.

> The spectrogram image is used **only for human validation**, never as the counting
> method. All counting is done on the numeric spectrogram so timestamps and
> frequencies are exact and wind can be filtered by frequency.

## Requirements

- Python 3.11+
- `ffmpeg` (used by `librosa`/`soundfile` for some formats)

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Quick start

No field audio is needed to try the pipeline — a synthetic sample generator
produces a recording with solo calls, a two-individual duet, and strong wind:

```bash
# 1. Generate a synthetic test recording (filename encodes date/time)
python src/generate_sample.py

# 2. Run detection on it (or point at a real recording / folder)
PYTHONPATH=src python src/detect.py data/audios/R20241011-180923.WAV
```

Outputs are written to `output/`:

- `output/<name>_spectrogram.png` — spectrogram with detected calls marked.
- `output/resultado.xlsx` — `Events`, `Files`, `By hour`, and `By month` sheets.

Process a whole folder of recordings at once:

```bash
PYTHONPATH=src python src/detect.py data/audios/
```

### Useful flags

| Flag | Meaning |
| --- | --- |
| `--lowcut` / `--highcut` | Band-pass limits in Hz (default 1500–4000). |
| `--threshold-k` | Detection sensitivity (median + k·MAD of band energy). |
| `--no-spectrogram` | Skip PNG rendering (faster batch runs). |
| `--output-dir` | Where to write outputs (default `output/`). |
| `--report` | Report filename (default `resultado.xlsx`). |

## How the recorder filename is read

Files like `R20241011-180923.WAV` embed the capture date (`20241011` → 2024-10-11)
and time (`180923` → 18:09:23). The pipeline parses this automatically to build the
hourly and monthly aggregates — no renaming needed.

## Project layout

```
src/
  bioacoustics/
    config.py         # tunable detection parameters (Phase 2 calibration)
    audio_io.py       # audio loading + filename date/time parsing
    detection.py      # bandpass, noise reduction, spectrogram, event + caller detection
    visualization.py  # spectrogram PNG for human validation
    report.py         # .xlsx report with hourly/monthly charts
    pipeline.py       # single-file orchestration
    api.py            # dashboard HTTP API (report + upload)
  generate_sample.py  # synthetic test-audio generator
  detect.py           # CLI entrypoint
tests/                # pipeline sanity tests
data/audios/          # put real recordings here (git-ignored)
data/uploads/         # POST /api/analyze scratch files (git-ignored)
output/               # generated artifacts (git-ignored)
```

## Calibration (Phase 2)

The defaults in `src/bioacoustics/config.py` target small Atlantic-forest hylids.
With a clean reference recording of the species, tune `lowcut_hz`/`highcut_hz` to the
real call band and `threshold_k` so wind never becomes a false positive.

## Roadmap status

- [x] **Phase 0** — environment + dependencies
- [x] **Phase 1** — core detection pipeline (this repo)
- [ ] **Phase 2** — calibration with a clean species reference
- [ ] **Phase 3** — Claude API validation of ambiguous chunks (`anthropic` already vendored)
- [ ] **Phase 4** — batch processing across all folders
- [ ] **Phase 5** — React + Vite dashboard

## Dashboard API

```bash
PYTHONPATH=src python -m bioacoustics.api   # http://127.0.0.1:8000
```

`GET /api/report` serves `output/resultado.json`. `POST /api/analyze` accepts multipart audio (`files` or `file`; `.wav`/`.flac`/`.ogg`/`.mp3`, max 10 files, 500 MB each), runs the pipeline, and writes the same JSON/xlsx reports. `GET /api/limits` returns those caps. Vite proxies `/api` to this server.

## Testing

```bash
PYTHONPATH=src pytest -q
```
