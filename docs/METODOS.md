# Métodos de detecção automática de vocalizações

Documento de métodos para o trabalho acadêmico sobre contagem automática de
canto de *Sphaenorhynchus caramaschii* (perereca-de-banhado). O texto descreve
o que o código **faz de fato** (`src/bioacoustics/`). Não substitui a revisão
bibliográfica. Números deste lote: `reports/campo_resumo.json` e
`output/resultado.xlsx`.

O que se pode afirmar com honestidade (calibração, restrições, o que **não**
é censo de indivíduos): `docs/PRECISAO_E_LIMITES.md`.

Implementação de referência:

| Etapa | Arquivo |
| --- | --- |
| Parâmetros | `src/bioacoustics/config.py` (`DetectionConfig`) |
| Leitura de áudio e data no nome | `src/bioacoustics/audio_io.py` |
| Filtro, STFT, limiar, eventos | `src/bioacoustics/detection.py` |
| Arquivos longos (janelas) | `src/bioacoustics/pipeline.py` |
| Excel e JSON | `src/bioacoustics/report.py` |
| PNG de conferência | `src/bioacoustics/visualization.py` |

## 1. Espécie-alvo

- Nome científico: *Sphaenorhynchus caramaschii*
- Nome comum usado no relatório: perereca-de-banhado
- Sinal de interesse: canto de anúncio com energia concentrada perto de
  **2,9 kHz** (ver calibração, sec. 8)

O detector **não** classifica espécie por aprendizado de máquina. Ele mede
energia na banda de frequência calibrada para essa espécie e trata picos
acima de um limiar adaptativo como eventos acústicos.

## 2. Material de campo

Cópia de trabalho em `data/field/` (não versionada; áudio de campo não entra
no Git). Nesta cópia: **75 arquivos** em seis pastas de *açude 1*:

| Pasta | Formato típico | Data no nome do arquivo |
| --- | --- | --- |
| `10_10_25 açude 1` | WAV ~1 h `RYYYYMMDD-HHMMSS.WAV` | sim |
| `12_09_25 açude 1` | MP3 de várias horas (`111009_001.MP3`, …) | **não** (ver abaixo) |
| `15_08_25 açude 1` | MP3 `Z0000002.MP3` etc. | **não** |
| `22_02_26 açude 1` | WAV `R…WAV` | sim |
| `24_10_25 açude 1` | WAV `R…WAV` | sim |
| `28_01_26 açude 1` | WAV `R…WAV` | sim |

Pasta **omitida** de propósito (instrução de campo): `15/08 açude 2 (esse nao precisa)`.
Essa pasta não está nesta cópia.

O gravador embute data e hora no nome no padrão `R20241011-180923.WAV`
(regex em `parse_recording_datetime`: `R?(\d{8})[-_](\d{6})`). MP3s como
`111009_001.MP3` e `Z0000002.MP3` **não** batem com esse padrão: `recorded_at`
fica vazio. Isso não impede a detecção, mas tira o arquivo dos gráficos por
hora e por mês (ver `docs/COMO_LER_OS_RESULTADOS.md`).

## 3. O que é contado (e o que não é)

Cada linha de resultado é um **evento acústico**: um trecho contínuo de
energia na banda da espécie acima do limiar, depois de fundir segmentos
muito próximos.

Isso **não** é:

- o número de indivíduos no açude;
- um censo populacional;
- uma classificação taxonômica independente.

`n_callers` / `max_simultaneous` estimam quantos picos espectrais distintos
aparecem **ao mesmo tempo** na banda (sec. 7). É um proxy de sobreposição de
cantos, não o tamanho da população.

## 4. Carregamento e taxa de amostragem

Áudio é lido em **mono**, reamostrado para **22 050 Hz** (`sample_rate`).
Arquivos curtos cabem na memória de uma vez. Arquivos mais longos que
`chunk_duration_s` (60 s) são lidos por fatias com `ffmpeg` (`load_audio_segment`),
sem decodificar a gravação inteira.

## 5. Filtro passa-faixa

Butterworth de ordem 4, **passa-faixa 2 600–3 200 Hz**, aplicado em fase zero
(`scipy.signal.sosfiltfilt`). O vento de açude (energia grave) fica fora da
banda. Harmônicos típicos em 5–8 kHz também ficam fora.

Antes do filtro, os primeiros e últimos 50 ms recebem um taper de cosseno,
para o `filtfilt` não “tilintar” nas bordas e inventar energia na banda.

## 6. Redução espectral de ruído

Com `use_noise_reduction=True` (padrão), aplica-se `noisereduce.reduce_noise`
com `prop_decrease=0.9`. Se a biblioteca não estiver instalada, o pipeline
segue só com o passa-faixa (degradação silenciosa).

## 7. Espectrograma numérico (STFT)

A contagem usa a **matriz de magnitude** da STFT, não a imagem PNG.

| Parâmetro | Valor padrão | Efeito |
| --- | --- | --- |
| `n_fft` | 2048 | janela ~93 ms a 22 050 Hz; resolução ~10,8 Hz/bin |
| `hop_length` | 512 | passo ~23 ms entre quadros |
| janela | Hann (`librosa.stft`) | padrão do librosa |

Só a soma das magnitudes **dentro da banda 2 600–3 200 Hz** entra no detector
(`band_energy` por quadro). O PNG (quando gerado) é conferência humana:
marcas verdes nos eventos e linha vermelha do limiar. A tese não deve tratar
o PNG como método de contagem.

## 8. Limiar adaptativo (mediana + k·MAD)

Para cada arquivo (ou cada janela de 60 s):

1. energia da banda por quadro;
2. mediana e MAD (desvio absoluto mediano);
3. limiar = `mediana + k · MAD` com **k = 6** (`threshold_k`);
4. quadros acima do limiar formam segmentos contínuos;
5. os primeiros e últimos `edge_guard_s` = 1,5 s de cada janela **não** entram
   na detecção (assentamento do filtro);
6. segmentos separados por no máximo `event_merge_gap_s` = 0,4 s viram um
   único evento;
7. eventos com duração &lt; `min_event_duration_s` = 0,05 s são descartados.

O campo `min_peak_distance_s` existe em `DetectionConfig` (0,15 s) mas **não
é usado** na implementação atual: a detecção é por corridas contínuas acima do
limiar, não por `find_peaks` na energia.

## 9. Regra de simultaneidade

Dentro de um evento, cada quadro da banda é inspecionado com `find_peaks`:

- altura mínima: `caller_rel_height` = 0,55 × pico mais forte do quadro
  (rejeita lóbulos laterais);
- distância mínima entre picos: `freq_separation_hz` = **400 Hz**.

`n_callers` do evento é o máximo de picos distintos entre os quadros do
evento. `max_simultaneous` do arquivo combina isso com eventos que se
sobreõem no tempo e têm frequências dominantes separadas por ≥ 400 Hz.

Calibração: valores mais apertados (p.ex. 250 Hz) contaram **sete**
“indivíduos” no clipe de referência de um único cantor, porque a crista em
~2,9 kHz vira vários picos. 400 Hz trata essa crista como um indivíduo.

## 10. Arquivos longos (chunking)

Gravações de 1–6 h não são carregadas inteiras.

- janela: 60 s (`chunk_duration_s`);
- sobreposição: 3 s (`chunk_overlap_s` = 2 × `edge_guard_s`);
- o passo efetivo faz as regiões úteis (sem as margens de 1,5 s) se
  encostarem, evitando duplicar eventos nas juntas;
- tempos dos eventos são deslocados para o relógio do arquivo;
- o PNG, se pedido, mostra só a **primeira** janela (`spectrogram_preview_s`).

O lote de campo desta análise usou `--no-spectrogram`: não há PNG por arquivo.

## 11. Calibração (Fase 2)

Referência limpa: `Áudio base/CEAES 2.m4a` (Drive), ~29 s.

- pico de energia do anúncio ~ **2,89 kHz**;
- quadros com voz aproximadamente **2,63–3,09 kHz**;
- banda operacional **2,6–3,2 kHz**.

Os padrões de `DetectionConfig` são esses valores calibrados, não os
anteriores à Fase 2.

## 12. Fase 3 (não utilizada)

A validação de trechos ambíguos por API Claude (`anthropic` em
`requirements.txt`) **não entra** nesta análise. Contagens vêm só do
processamento de sinal (Fases 0–2 e 4). Eventos duvidosos exigem conferência
humana (PNG quando gerado, ou escuta pontual).

## 13. Limitações (importante para a tese)

Lista curta abaixo. Frases prontas para a tese e o que **não** afirmar:
`docs/PRECISAO_E_LIMITES.md`.

1. **Evento ≠ indivíduo no açude.** Um macho que canta muitas vezes gera
   muitos eventos. Dois machos no mesmo pitch podem fundir-se em um evento.
2. **Falsos positivos na banda.** Qualquer ruído em 2,6–3,2 kHz acima do
   limiar (inseto, vento residual, gravador, outra espécie) vira evento. Neste
   lote, a mediana nos WAV foi **~1 600 eventos/hora** (mín. 315, máx. 3 014).
   Isso **pode incluir ruído** — a calibração foi no recorte limpo CEAES 2,
   não no açude. Não use o total bruto como “número de machos” sem amostragem
   de conferência.
3. **Limiar por janela.** Cada 60 s tem a própria mediana/MAD. Coro contínuo
   ou silêncio prolongado mudam o limiar ao longo da noite.
4. **Agregados hora/mês.** Usam a data/hora **do nome do arquivo**, não o
   instante de cada evento. Um WAV que começa às 18:09 coloca *todos* os
   eventos na hora 18, inclusive os dos minutos 50+. MP3s sem padrão `R…`
   saem dos gráficos.
5. **Relatórios só no fim do CLI.** `output/resultado.xlsx` e
   `output/resultado.json` são gravados quando o lote **termina**. Totais
   oficiais deste lote: 75 arquivos, 149 962 eventos, 104,7 h. Cópia enxuta no
   Git: `reports/campo_resumo.json`.
6. **PNG ausente neste lote.** Conferência visual arquivo a arquivo exige
   rerodar sem `--no-spectrogram` (e, em arquivos de horas, só o preview de
   60 s).

## 14. Relatórios gerados

O mesmo lote produz **os dois** produtos (detalhe em
`docs/COMO_LER_OS_RESULTADOS.md`):

- **Excel** `output/resultado.xlsx` — tabelas para Word, R, SPSS;
- **JSON** `output/resultado.json` — contrato do painel web.

Como reproduzir o lote: `docs/REPRODUTIBILIDADE.md`. No Mac, o ambiente (Python 3.11+, ffmpeg): `docs/INSTALACAO_MAC.md`.
