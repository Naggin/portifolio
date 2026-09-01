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

## Relatórios: Excel **e** painel web (os dois)

A aluna **não escolhe** entre planilha e gráfico. Cada lote grava os dois:

| Produto | Arquivo | Uso |
| --- | --- | --- |
| **Excel provisório** | [`reports/relatorio_provisorio.xlsx`](reports/relatorio_provisorio.xlsx) | Planilha **partilhável** (e-mail, rascunho da tese): resumo, campanhas, gráficos e recorte para ouvir. Marcada **PROVISÓRIO**. Sem as 149 962 linhas. |
| **Excel completo** | `output/resultado.xlsx` | Lista local de todos os eventos (~7 MB, gitignored). Abas `Events`, `Files`, `By hour`, `By month`. |
| **Painel** | `web/` + `output/resultado.json` | Cartões, gráficos por hora/mês e tabelas no navegador. |
| **PNG** | `output/<arquivo>_spectrogram.png` | Conferência humana. **Este lote de campo usou `--no-spectrogram`** — não há PNG. |

O CLI só escreve o `.xlsx` e o `.json` **quando termina todos os arquivos**.
Este lote de campo **terminou**: 75 arquivos, 104,7 h, 149 962 eventos
(resumo em `reports/campo_resumo.json`; Excel provisório em
`reports/relatorio_provisorio.xlsx`; Excel/JSON completos em `output/`,
gitignored).

Documentação para a orientadora (português):

- [docs/PRECISAO_E_LIMITES.md](docs/PRECISAO_E_LIMITES.md) — **o que a tese pode afirmar**: calibração, restrições, lote completo; o que **não** é censo nem prova de espécie em cada evento
- [docs/INSTALACAO_MAC.md](docs/INSTALACAO_MAC.md) — **Instalação no Mac** (pipeline Python, ffmpeg, painel opcional)
- [docs/METODOS.md](docs/METODOS.md) — espécie, banda, STFT, limiar MAD, simultaneidade, chunking, o que é contado, limitações
- [docs/COMO_LER_OS_RESULTADOS.md](docs/COMO_LER_OS_RESULTADOS.md) — cada aba do Excel, campos JSON, como abrir o painel
- [docs/REPRODUTIBILIDADE.md](docs/REPRODUTIBILIDADE.md) — comandos e padrões de `DetectionConfig`

## Requirements

- Python 3.11+
- `ffmpeg` (used by `librosa`/`soundfile` for some formats)

**Instalação no Mac:** [docs/INSTALACAO_MAC.md](docs/INSTALACAO_MAC.md) (`brew install python@3.12 ffmpeg`, venv, lote local do Drive). No Linux/Windows, os comandos abaixo.

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

Outputs are written to `output/` (gitignored):

- `output/resultado.xlsx` — Excel for thesis tables (Events, Files, By hour, By month + charts).
- `output/resultado.json` — same results for the React dashboard (`GET /api/report`).
- `output/<name>_spectrogram.png` — spectrogram with detected calls marked (omit with `--no-spectrogram`).

Process a whole folder of recordings at once:

```bash
PYTHONPATH=src python src/detect.py data/audios/
```

Field copy from the shared Drive (hour-scale WAVs/MP3s under `data/field/`, not committed):

```bash
PYTHONPATH=src python src/detect.py data/field --no-spectrogram
```

Skip folder `15/08 açude 2 (esse nao precisa)` if it is present. MP3s such as
`111009_001.MP3` are analysed but have `recorded_at` null, so they drop out of
the hour/month sheets — see [docs/COMO_LER_OS_RESULTADOS.md](docs/COMO_LER_OS_RESULTADOS.md).

### Useful flags

| Flag | Meaning |
| --- | --- |
| `--lowcut` / `--highcut` | Band-pass limits in Hz (default 2600–3200). |
| `--threshold-k` | Detection sensitivity (median + k·MAD of band energy). |
| `--no-spectrogram` | Skip PNG rendering (faster batch runs). |
| `--output-dir` | Where to write outputs (default `output/`). |
| `--report` | Excel filename (default `resultado.xlsx`). |
| `--json-report` | JSON filename (default `resultado.json`). |

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
    report.py         # .xlsx + JSON (dashboard contract)
    pipeline.py       # single-file orchestration
    api.py            # dashboard HTTP API (report + upload)
  generate_sample.py  # synthetic test-audio generator
  detect.py           # CLI entrypoint
docs/                 # instalação Mac, métodos, como ler resultados, reprodutibilidade (PT)
scripts/              # download Drive, resumo do lote, Excel provisório
reports/              # campo_resumo.json + relatorio_provisorio.xlsx (sem WAV)
tests/                # pipeline sanity tests
web/                  # React + Vite dashboard
data/audios/          # put real recordings here (git-ignored)
data/field/           # Drive field copy (git-ignored; do not commit)
data/uploads/         # POST /api/analyze scratch files (git-ignored)
output/               # resultado.xlsx + resultado.json + PNGs (git-ignored)
```

## Calibration (Phase 2)

Defaults in `src/bioacoustics/config.py` were tuned on the clean species
reference `Áudio base/CEAES 2.m4a` (Drive): advertisement energy peaks near
**2.89 kHz** (voiced frames ~2.63–3.09 kHz). The detector band is **2.6–3.2 kHz**
so pond wind and 5–8 kHz harmonics are ignored. Simultaneous-caller spacing is
400 Hz — the uncalibrated settings counted seven “individuals” on that
single-species clip because they treated the 2.9 kHz ridge as many peaks.

Field folders on the shared Drive are hour-scale `RYYYYMMDD-HHMMSS.WAV` files
(and some multi-hour MP3s). Skip `15/08 açude 2 (esse nao precisa)`. Long
files are processed in 60 s overlapping chunks so they are never loaded whole.

## Roadmap status

- [x] **Phase 0** — environment + dependencies
- [x] **Phase 1** — core detection pipeline (this repo)
- [x] **Phase 2** — calibration with a clean species reference (`CEAES 2`)
- [ ] **Phase 3** — Claude API validation of ambiguous chunks (`anthropic` already vendored)
- [x] **Phase 4** — chunked processing of hour-scale files (folder batch still via CLI)
- [x] **Phase 5** — React + Vite dashboard

## Dashboard (gráficos no navegador)

Com `resultado.json` já gerado (ou o lote de campo em `web/public/campo/`):

```bash
PYTHONPATH=src python -m bioacoustics.api   # http://127.0.0.1:8000
cd web && npm install && npm run dev       # http://127.0.0.1:5173  (proxy /api → :8000)
```

`GET /api/report` serves `output/resultado.json`. Sem a API, o painel carrega o lote de campo em `web/public/campo/resultado.json` (totais reais; tabela de eventos amostrada — o Excel tem todos). Regenerar esse JSON com `python3 scripts/export_campo_dashboard.py`.

`POST /api/analyze` accepts multipart audio (`files` or `file`; `.wav`/`.flac`/`.ogg`/`.mp3`/`.m4a`, max 10 files, 2 GB each), runs the pipeline in 60 s chunks for long files, and writes the same JSON/xlsx reports **and** spectrogram PNGs. `GET /api/limits` returns those caps. Vite proxies `/api` to this server.

O upload do painel não substitui o lote CLI dos 75 arquivos de campo.

## Testing

```bash
PYTHONPATH=src pytest -q
```
