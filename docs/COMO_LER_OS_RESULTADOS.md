# Como ler os resultados

A análise gera **dois produtos**, de propósito diferentes. Não é uma escolha
entre planilha e gráfico: a aluna fica com os dois.

| Produto | Onde | Para quê |
| --- | --- | --- |
| **Excel** | `output/resultado.xlsx` | Tabelas da tese, Excel, R, SPSS |
| **Painel web** | `web/` lê `GET /api/report` (`resultado.json`) | Gráficos e tabelas no navegador |
| **JSON** | `output/resultado.json` | Mesmo conteúdo do painel; arquivo intermediário |
| **PNG** | `output/<nome>_spectrogram.png` | Conferência humana (este lote: **não gerado**) |

`output/` está no `.gitignore`. Depois que o `detect.py` **terminar**, copie
a planilha para um pendrive/Drive da tese. Enquanto o processo estiver
rodando, esses arquivos ainda não existem — o CLI só os grava no final.

**Estado deste lote (campo):** em processamento. O log
`output/analyze.log` mostra arquivos já concluídos, mas isso **não** é o
relatório final. Não use totais parciais como número de tese.

## 1. Excel — `resultado.xlsx`

Gerado por `write_report` em `src/bioacoustics/report.py` (openpyxl). Quatro
abas, mais dois gráficos de barras embutidos.

### Aba `Events` (uma linha por evento)

| Coluna | Significado |
| --- | --- |
| `file` | Nome do arquivo (não o caminho da pasta) |
| `recorded_at` | Data/hora extraída do nome, ISO 8601; vazio se o nome não for `RYYYYMMDD-HHMMSS` |
| `event` | Índice do evento **dentro daquele arquivo** (começa em 1) |
| `start_s` | Início do evento, segundos desde o começo do arquivo |
| `end_s` | Fim do evento (s) |
| `peak_time_s` | Instante da energia máxima (s) |
| `peak_freq_hz` | Frequência dominante no pico (Hz), restrita à banda |
| `energy` | Energia da banda no quadro de pico (unidade relativa) |
| `n_callers` | Picos espectrais simultâneos estimados naquele evento |

Não há coluna de duração nesta aba. Duração = `end_s − start_s`, ou use o
campo `duration_s` do JSON.

Importar em R: `readxl::read_excel("resultado.xlsx", sheet = "Events")`.
SPSS: *File → Open → Excel*, escolher a aba.

### Aba `Files` (uma linha por gravação)

| Coluna | Significado |
| --- | --- |
| `file` | Nome do arquivo |
| `recorded_at` | Igual à aba Events (vazio nos MP3 `111009_001` / `Z0000002`) |
| `duration_s` | Duração da gravação (s) |
| `n_events` | Quantidade de eventos acústicos |
| `max_simultaneous` | Máximo de cantores simultâneos estimado no arquivo |

### Aba `By hour`

24 linhas, horas 0–23. `n_events` é a **soma dos eventos de todos os
arquivos cuja `recorded_at.hour` é aquela hora**. Gráfico de barras
“Calls by hour of day” na célula `D2`.

Arquivos **sem** `recorded_at` **não entram**. Eventos não são
redistribuídos ao longo da duração: um WAV de 1 h que começa às 18:09
contribui com *todos* os seus eventos para a hora 18.

### Aba `By month`

12 linhas, meses 1–12. Mesma lógica: soma por `recorded_at.month`.
Gráfico “Calls by month” em `D2`. MP3s sem data no nome não entram.

## 2. JSON — `resultado.json` (painel)

Gerado por `write_json_report` / `build_report_payload`. O dashboard React
(`web/src/lib/types.ts`) espera exatamente este contrato.

### Metadados

```json
{
  "generated_at": "…ISO UTC…",
  "species": "Sphaenorhynchus caramaschii",
  "common_name": "perereca-de-banhado",
  "config": {
    "sample_rate": 22050,
    "lowcut_hz": 2600.0,
    "highcut_hz": 3200.0,
    "threshold_k": 6.0
  },
  "summary": {
    "n_files": 0,
    "n_events": 0,
    "max_simultaneous": 0,
    "total_duration_s": 0.0
  }
}
```

`summary.n_events` é a soma de eventos de **todos** os arquivos do lote,
incluindo MP3s sem data. Já `by_hour` / `by_month` **excluem** esses MP3s.
Por isso o total do resumo pode ser maior que a soma das barras.

### `files[]`

Além das colunas da aba Files:

| Campo | Significado |
| --- | --- |
| `threshold` | Limiar mediana + k·MAD usado na detecção daquele arquivo (no chunking, o da primeira janela) |
| `spectrogram` | Nome esperado do PNG, p.ex. `R20241011-180923_spectrogram.png` |
| `band_energy` | Série `{ times_s, energy }` **reduzida a no máximo 400 pontos** |

Não copie `band_energy` para um anexo da tese: em arquivos de horas o vetor
completo é enorme; o JSON já vem subamostrado.

### `events[]`

Iguais à aba Events, mais `duration_s`.

### `by_hour` / `by_month`

Listas `{ "hour": 0–23, "n_events": … }` e `{ "month": 1–12, "n_events": … }`.

## 3. Abrir o painel web

Dois processos, em dois terminais, na raiz do repositório. No Mac, o ambiente (Python, ffmpeg, Node) está em `docs/INSTALACAO_MAC.md`.

```bash
# 1. API que serve output/resultado.json
PYTHONPATH=src python3 -m bioacoustics.api
# http://127.0.0.1:8000/api/report

# 2. Interface
cd web
npm install          # só na primeira vez
npm run dev
```

O Vite (porta padrão **5173**) encaminha `/api` para `127.0.0.1:8000`
(`web/vite.config.ts`).

O que aparece:

- cartões: arquivos, eventos, máximo simultâneo, duração total;
- gráficos de barras por hora e por mês (Recharts);
- tabela de arquivos, com botão “Ver PNG”;
- tabela de eventos, filtrável por nome de arquivo.

Se a API estiver fora ou `resultado.json` ainda não existir, o painel cai no
**demo** em `web/public/demo/resultado.json` (áudio sintético, não é campo).
Há também “Abrir resultado.json” para carregar um JSON baixado à mão.

Neste lote de campo (`--no-spectrogram`), “Ver PNG” mostra
“Espectrograma indisponível”: o arquivo não foi renderizado. Isso é
esperado.

Upload pelo painel (`POST /api/analyze`) é para poucos arquivos curtos (máx.
10, 2 GB cada) e **gera PNG**. Não substitua o lote CLI de 75 arquivos por
esse upload.

## 4. Nomes de arquivo e gráficos de hora/mês

Parser (`src/bioacoustics/audio_io.py` e `web/src/lib/filename.ts`):

```
R20241011-180923.WAV  →  2024-10-11 18:09:23
```

`R` opcional; data `YYYYMMDD`; separador `-` ou `_`; hora `HHMMSS`.

| Exemplo | `recorded_at` | Entra em hora/mês? |
| --- | --- | --- |
| `R20241011-180923.WAV` | 2024-10-11 18:09:23 | sim |
| `111009_001.MP3` | `null` | **não** |
| `Z0000002.MP3` | `null` | **não** |

Os eventos desses MP3 **entram** em `Events`, `Files` e `summary.n_events`.
Só as agregações temporais os ignoram. Para incluir setembro/agosto nos
gráficos, seria preciso data no nome (ou metadados externos) — isso **não**
está implementado.

O painel avisa quando um upload não parece `R20241011-180923.WAV`.

## 5. Espectrograma PNG

`src/bioacoustics/visualization.py`: duas faixas (espectrograma + energia da
banda), marcas nos eventos, linhas da banda e do limiar. **Não entra na
contagem.**

Comando deste lote:

```bash
PYTHONPATH=src python3 src/detect.py data/field --no-spectrogram
```

Arquivos de várias horas, mesmo com PNG, só mostram os primeiros 60 s.

## 6. Cópia enxuta no repositório

`output/` não é commitado. Se `resultado.json` **completo** existir, uma cópia
enxuta (por arquivo: nome, `recorded_at`, duração, `n_events`,
`max_simultaneous` — **sem** `band_energy` nem a lista de eventos) pode ir
para `reports/campo_resumo.json`. Enquanto o lote estiver incompleto, esse
arquivo **não** deve ser tratado como resultado da tese.
