# Como ler os resultados

A análise gera **dois produtos**, de propósito diferentes. Não é uma escolha
entre planilha e gráfico: a aluna fica com os dois.

| Produto | Onde | Para quê |
| --- | --- | --- |
| **Excel provisório** | `reports/relatorio_provisorio.xlsx` | Livro **partilhável** (e-mail, tese): resumo, campanhas, gráficos, recorte para ouvir. Marcado **PROVISÓRIO**. |
| **Excel completo** | `output/resultado.xlsx` | Lista local de **todos** os eventos (~7 MB, gitignored) |
| **Painel web** | `web/` lê `GET /api/report` (`resultado.json`) | Gráficos e tabelas no navegador |
| **JSON** | `output/resultado.json` | Mesmo conteúdo do painel; arquivo intermediário |
| **PNG** | `output/<nome>_spectrogram.png` e, sob pedido, `output/event_spectrograms/` | Conferência humana. Arquivo longo: janela com picos. Por arquivo: painel Arquivos → Ver PNG (sob pedido se o lote usou `--no-spectrogram`). Por evento: painel Eventos → Ver espectrograma. Tese: aba `Espectrogramas`. |

O ficheiro para enviar e abrir na tese é
`reports/relatorio_provisorio.xlsx` (versionado; regenerar com
`python3 scripts/export_relatorio_provisorio.py`). A lista completa de
eventos continua só na máquina local: `output/resultado.xlsx` (~7 MB).
`output/` está no `.gitignore`. O CLI só grava o Excel/JSON completos
**quando termina todos os arquivos**.

Como citar o número sem inflar o que ele significa (evento ≠ indivíduo;
banda calibrada, não prova taxonómica em cada linha):
`docs/PRECISAO_E_LIMITES.md`.

**Estado deste lote (campo):** concluído em 2026-09-01. 75 arquivos, 104,7 h,
149 962 eventos, `max_simultaneous` = 2, 0 erros. Resumo commitável:
`reports/campo_resumo.json`. Planilha provisória versionada:
`reports/relatorio_provisorio.xlsx`. Totais oficiais também em
`output/resultado.xlsx` (máquina local, não no Git).

## 0. Excel provisório — `relatorio_provisorio.xlsx`

Livro pequeno para partilhar. Abas em português, faixa **PROVISÓRIO** no
topo: `Leia primeiro`, `Resumo`, `Campanhas`, `Arquivos`, `Por hora`,
`Por mês`, `Ouvir`, `Espectrogramas`, `Parâmetros`. Não traz as 149 962
linhas de eventos.

A aba `Ouvir` é o recorte de validação já escolhido:
`10_10_25 açude 1` / `R20241012-041002.WAV`, seek **30:45** (60 s),
relógio 04:40:47–04:41:47. Não começar pelo WAV das 9:10
(`R20241012-091022.WAV`). Se o script correr com `output/resultado.json`
local, a mesma aba lista os 64 eventos desse minuto.

A aba `Espectrogramas` embute esse minuto (e um zoom no pico mais forte)
com os eventos marcados. É validação, não o método de contagem. PNG em
`reports/espectrogramas/`.

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
- tabela de arquivos (**Ver PNG** gera sob pedido quando a API está no ar; coluna oculta
  só no JSON estático de campo sem API);
- tabela de eventos, filtrável por nome de arquivo (amostra no JSON do painel);
  cada linha tem **Ver espectrograma** (sob pedido, áudio local).

Se a API estiver fora, o painel cai no lote de campo em
`web/public/campo/resultado.json` (75 arquivos, totais reais). A tabela de
eventos é uma amostra; o Excel tem todos. Há também “Abrir resultado.json”
para carregar um JSON baixado à mão.

Neste lote (`--no-spectrogram`) o JSON estático em `web/public/campo/` **não**
expõe a coluna de espectrograma por arquivo. Com a **API local** e o WAV em
`data/field/`, **Ver PNG** na tabela Arquivos gera
`GET /api/spectrograms/{stem}_spectrogram.png` sob pedido (janela de 60 s mais
densa, picos marcados). **Por evento**, o botão *Ver espectrograma* pede
`GET /api/event-spectrogram` e desenha só aquela captura (com o Pico da linha).
Sem o WAV nesta máquina, a API responde que o áudio não está disponível. Upload
pela API gera PNG de arquivo inteiro num lote novo.

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

### Espectrograma por arquivo (tabela Arquivos do painel)

Sob pedido quando o PNG ainda não existe (lote com `--no-spectrogram`): Arquivos →
**Ver PNG**. A API (`GET /api/spectrograms/{stem}_spectrogram.png`) localiza o
WAV em `data/field/` (ou uploads), lê os eventos desse arquivo em
`output/resultado.json` e desenha a **janela de 60 s com mais picos** (ou o
ficheiro inteiro se for curto), com os picos marcados — a mesma lógica do
pipeline. O PNG fica em cache em `output/` (gitignored). A primeira chamada
pode demorar em gravações de 1 h; as seguintes servem o ficheiro em cache.
Sem o áudio nesta máquina, a resposta indica que o áudio não está disponível.

### Espectrograma por evento (tabela Eventos do painel)

Sob pedido: no dashboard, Eventos → **Ver espectrograma**. A API
(`GET /api/event-spectrogram`) carrega só uns segundos de contexto à volta
daquela linha (`start_s`/`end_s` + ~1,25 s, limitado ao ficheiro) e marca o
**Pico** da tabela (`peak_time_s`, `peak_freq_hz`) — linha vertical e círculo
verde. Não re-corre a detecção; a imagem prova essa linha, não a identidade
da espécie. `Indiv.` / `n_callers` na legenda = cantores simultâneos
estimados, não um indivíduo etiquetado. Os PNG ficam em
`output/event_spectrograms/` (gitignored); **não** há 149 962 ficheiros no
Git. Sem o WAV em `data/field/` (ou uploads) nesta máquina, a resposta é
que o áudio não está disponível. Os três PNG da galeria `/espectrogramas/`
são só o recorte de validação 30:45, não um substituto por linha.

Comando deste lote:

```bash
PYTHONPATH=src python3 src/detect.py data/field --no-spectrogram
```

Arquivos de várias horas, mesmo com PNG, mostram a **janela de 60 s com
mais picos**, não os primeiros 60 s. A tese usa a aba `Espectrogramas`
(`reports/espectrogramas/`), o recorte 30:45 da madrugada.

## 6. Cópia enxuta no repositório

`output/` não é commitado (`resultado.json` ~43 MB; `resultado.xlsx` ~7 MB).
A cópia enxuta (por arquivo: campanha, nome, `recorded_at`, duração, `n_events`,
`max_simultaneous`, eventos/hora — **sem** `band_energy` nem a lista de
eventos) está em `reports/campo_resumo.json`, gerada por
`scripts/summarize_campo.py`. O Excel **provisório** partilhável
(`reports/relatorio_provisorio.xlsx`) sai de
`python3 scripts/export_relatorio_provisorio.py`.
