# Reprodutibilidade

Comandos e parâmetros para repetir a detecção. Valores abaixo são os
**padrões de `DetectionConfig`** no código, não um resultado de campo.

## Ambiente

- Python **3.11+** (ambiente desta análise: 3.12.3)
- `ffmpeg` no `PATH` (leitura de `.m4a` / seek em arquivos longos)
- `ffprobe` opcional (duração sem decodificar o arquivo inteiro)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Dependências principais (`requirements.txt`): `librosa`, `numpy`, `scipy`,
`noisereduce`, `matplotlib`, `openpyxl`, `soundfile`, `pytest`.
`anthropic` está listado para a Fase 3 e **não é chamado** neste pipeline.

Painel: Node.js com `cd web && npm install`.

## Áudio de demonstração (sem Drive)

```bash
python3 src/generate_sample.py
PYTHONPATH=src python3 src/detect.py data/audios/R20241011-180923.WAV
```

Saída em `output/`: PNG, `resultado.xlsx`, `resultado.json`.

Testes:

```bash
PYTHONPATH=src pytest -q
```

## Lote de campo (Drive)

Áudio em `data/field/` (gitignored; dezenas de GB). **Não** versionar WAV/MP3.

Omitir a pasta `15/08 açude 2 (esse nao precisa)` se ela estiver na cópia.

```bash
PYTHONPATH=src python3 src/detect.py data/field --no-spectrogram \
  --output-dir output \
  --report resultado.xlsx \
  --json-report resultado.json
```

O CLI percorre a pasta com `rglob` e aceita `.wav`, `.flac`, `.ogg`, `.mp3`,
`.m4a`. Só no **fim** de todos os arquivos escreve o Excel e o JSON. Um log
como `output/analyze.log` é só progresso; não é o relatório.

Bandeiras úteis:

| Flag | Padrão | Função |
| --- | --- | --- |
| `--lowcut` / `--highcut` | 2600 / 3200 | Limites do passa-faixa (Hz) |
| `--threshold-k` | 6.0 | Multiplicador MAD |
| `--no-spectrogram` | off | Não gera PNG (lote longo) |
| `--output-dir` | `output` | Destino |
| `--report` | `resultado.xlsx` | Nome do Excel |
| `--json-report` | `resultado.json` | Nome do JSON |

## Painel

```bash
PYTHONPATH=src python3 -m bioacoustics.api          # :8000
cd web && npm run dev                                # :5173, proxy /api → :8000
```

## Padrões de `DetectionConfig`

Fonte: `src/bioacoustics/config.py`. Calibração: `CEAES 2.m4a` (Fase 2).

| Parâmetro | Padrão | Uso |
| --- | --- | --- |
| `sample_rate` | 22050 | Hz, mono |
| `lowcut_hz` | 2600 | passa-faixa |
| `highcut_hz` | 3200 | passa-faixa |
| `filter_order` | 4 | Butterworth + `sosfiltfilt` |
| `n_fft` | 2048 | STFT |
| `hop_length` | 512 | STFT |
| `use_noise_reduction` | True | `noisereduce` |
| `noise_reduce_prop_decrease` | 0.9 | intensidade do denoise |
| `threshold_k` | 6.0 | limiar = mediana + k·MAD |
| `min_peak_distance_s` | 0.15 | **declarado; não usado** em `detect_events` |
| `event_merge_gap_s` | 0.4 | funde segmentos próximos |
| `min_event_duration_s` | 0.05 | descarta eventos curtos demais |
| `freq_separation_hz` | 400 | picos = cantores distintos |
| `caller_rel_height` | 0.55 | fração do pico do quadro |
| `edge_guard_s` | 1.5 | margem morta nas pontas da janela |
| `chunk_duration_s` | 60 | arquivos longos |
| `chunk_overlap_s` | 3 | 2 × `edge_guard_s` |
| `spectrogram_preview_s` | 60 | PNG só da primeira janela |

## O que não entra no Git

- `data/field/` — gravações de campo
- `data/audios/*` — amostras locais (exceto `.gitkeep`)
- `data/uploads/` — uploads da API
- `data/reference/` — áudio de calibração
- `output/` — Excel, JSON e PNG gerados

O método está no código e em `docs/METODOS.md`. Os números de um lote concreto
estão em `output/resultado.xlsx` depois que o processo **termina**.
