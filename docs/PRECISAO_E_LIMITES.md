# Precisão tentada e limites do que se pode afirmar

Documento para a tese: o que foi feito para o detector ser **o mais preciso
possível dentro do método escolhido**, e o que **não** se afirma. Complementa
`docs/METODOS.md` (como o algoritmo funciona) e
`docs/COMO_LER_OS_RESULTADOS.md` (como ler Excel/JSON).

A pergunta que este texto responde não é “o número está certo?”. É: **o
pipeline foi calibrado, restringido e documentado de forma que a contagem
automática não seja um palpite solto?** Sim. Isso **não** equivale a dizer
que cada evento é um macho da espécie no açude.

## 1. Afirmação que o trabalho sustenta

Neste lote, o mesmo `DetectionConfig` (banda 2,6–3,2 kHz, limiar
mediana + 6·MAD, simultaneidade com separação de 400 Hz) foi aplicado a
**75 arquivos**, **104,7 h**, **0 erros de processamento**. A saída é uma
lista de **eventos acústicos** (picos de energia na banda calibrada, com
instante e frequência), não um censo de indivíduos nem uma classificação
taxonômica.

Totais: `reports/campo_resumo.json` e `output/resultado.xlsx`. Parâmetros:
`src/bioacoustics/config.py`.

## 2. O que foi feito para ser preciso

Cada item abaixo é uma escolha concreta no código, não uma intenção genérica.

### 2.1 Calibração na espécie, não numa banda “larga de anuro”

A banda **não** ficou em 1,5–4 kHz (intervalo amplo que captura vento,
insetos e outras espécies). Foi fechada a partir do recorte limpo
`Áudio base/CEAES 2.m4a` (~29 s):

- pico do anúncio ~ **2,89 kHz**;
- energia com voz ~ **2,63–3,09 kHz**;
- banda operacional **2 600–3 200 Hz**.

Assim, ruído de baixa frequência (vento no gravador) **não entra** como
canto. Teste de regressão: vento sintético a ~90–150 Hz não gera eventos
(`tests/test_detection.py`).

### 2.2 Contagem no espectrograma numérico, não na imagem

O PNG existe só para conferência humana. Eventos, tempos e frequências
saem da matriz STFT (`n_fft=2048`, `hop_length=512`, `sample_rate=22050`).
Não há “contar bolhas no gráfico”.

### 2.3 Limiar adaptativo, não um valor fixo de amplitude

O critério é **mediana + k·MAD** da energia na banda, com `threshold_k=6`,
**por janela de 60 s**. Arquivos com vento variável ou coro denso não
usam o mesmo limiar absoluto de um trecho silencioso. Eventos com
intervalo ≤ 0,4 s são fundidos (`event_merge_gap_s`); duração mínima
0,05 s.

### 2.4 Correção explícita de supercontagem de indivíduos

Antes da calibração, picos laterais do **mesmo** anúncio (banda larga,
`freq_separation_hz=250`, `caller_rel_height=0.3`) produziam até **sete
“indivíduos”** no recorte de uma espécie. Os padrões atuais
(`freq_separation_hz=400`, `caller_rel_height=0.55`) tratam a crista
~200 Hz em torno de 2,9 kHz como **um** cantor. No lote de campo,
`max_simultaneous` ficou em **2** em todos os arquivos — coerente com a
banda de 600 Hz e a separação de 400 Hz (cabem no máximo ~dois picos
distintos). Isso é teto estrutural, não prova de que havia só dois machos
no açude.

### 2.5 Arquivos longos sem perder bordas nem duplicar juntas

WAV/MP3 de horas não cabem na RAM de uma vez. Processamento em janelas
de 60 s com sobreposição de 3 s e exclusão de 1,5 s em cada borda
(filtro zero-phase). As regiões úteis se encostam: nada real é descartado
nas juntas, e eventos não são contados duas vezes. Teste:
`test_chunked_processing_matches_full_file`.

### 2.6 Lote completo, mesmos parâmetros, pastas fora de propósito excluídas

- 75 arquivos das campanhas de *açude 1*;
- **não** incluídos: `15/08 açude 2 (esse nao precisa)` e `Áudio base`
  (este último só calibração);
- 0 falhas de leitura/processamento;
- comando reproduzível em `docs/REPRODUTIBILIDADE.md`.

### 2.7 O que não se misturou com a contagem

A Fase 3 (API Claude / `anthropic`) **não foi usada**. Validação por
modelo de linguagem não entra no número. Contagem = só processamento de
sinal. Trechos duvidosos pedem ouvido humano, não um segundo algoritmo
opaco.

### 2.8 Limitações escritas no mesmo repositório que o número

Os totais no Excel não circulam sozinhos. Há ressalvas no resumo
(`reports/campo_resumo.json` → `caveats`), em `docs/METODOS.md` §13 e
neste arquivo. Agregados por hora/mês que **omitam** 7 MP3s sem data no
nome e que usem a hora do **início do arquivo** estão descritos, não
escondidos.

## 3. O que a precisão **não** cobre

Ser preciso no detector **não** autoriza estas frases na tese:

| Não afirmar | Por quê |
| --- | --- |
| “149 962 indivíduos” ou “número de machos no açude” | Um macho gera muitos eventos; dois machos no mesmo pitch podem virar um. |
| “Todo evento da manhã é *S. caramaschii*” | Qualquer energia na banda acima do limiar vira evento (inseto, gravador, outra espécie). Calibração no CEAES 2 limpo, **não** no açude ruidoso. Mediana ~1 600 eventos/h nos WAV. |
| “Confirmámos espécie até de manhã” | Este lote rodou com `--no-spectrogram`. Não houve escuta sistemática nem PNG por arquivo. |
| “O gráfico por hora é o relógio de cada canto” | A hora vem do nome `RYYYYMMDD-HHMMSS` no **início** do ficheiro. Um WAV das 18:09 põe **todos** os eventos na hora 18. Sete MP3s (50 170 eventos) **não entram** nos gráficos hora/mês. Zeros às 11–13 h: **não havia WAV a começar nessa hora**, não “zero canto”. |
| “Validação por inteligência artificial” | Claude não foi chamado. |
| “Dois indivíduos simultâneos no açude” | `n_callers` / `max_simultaneous=2` é o máximo que a banda+separação consegue resolver, não um recenseamento. |

`min_peak_distance_s` existe em `DetectionConfig` e **não é usado** no
detector. Não citar esse campo como critério aplicado.

## 4. Frases que a tese pode usar (e as que deve evitar)

**Usar (fiel ao método):**

> A detecção automática foi calibrada no recorte de referência da espécie
> (*Áudio base/CEAES 2*), com banda restrita a 2,6–3,2 kHz, limiar
> adaptativo (mediana + 6·MAD) e contagem sobre o espectrograma numérico.
> Os mesmos parâmetros foram aplicados a 75 gravações (104,7 h), com zero
> falhas de processamento. O produto é o número de **eventos acústicos na
> banda calibrada**, reproduzível a partir de `DetectionConfig`.

> Antes da calibração, o mesmo anúncio gerava vários “indivíduos”
> espectrais; a separação em frequência e a altura relativa dos picos
> foram ajustadas para não fragmentar um cantor.

**Não usar:**

> O algoritmo identificou 149 962 pererecas / machos / indivíduos da
> espécie ao longo da campanha.

> Comprovámos que a espécie canta até às 10 h da manhã em todos os
> eventos detetados.

## 5. O que ainda aumentaria a certeza (e não foi feito neste lote)

Não é falha do texto: é o próximo passo **se** a tese quiser afirmar
espécie no campo, não só energia na banda.

1. Amostra de conferência humana (escuta ou PNG) em trechos de madrugada
   **e** de manhã, vários arquivos, com taxa de verdadeiro/falso positivo.
2. Recalibrar o limiar num trecho ruidoso do açude, não só no CEAES 2.
3. Relógio por evento (`recorded_at` + `peak_time_s`) nos gráficos
   hora/mês, e data para os 7 MP3s sem padrão `R…`.
4. Fase 3 só como apoio pontual a trechos ambíguos, **depois** da
   amostragem humana — não como substituto da contagem.

Enquanto isso não existir, a honestidade do trabalho está em **não
confundir precisão do detector com prova de identidade de cada evento**.

## 6. Onde conferir cada afirmação

| Afirmação | Onde está |
| --- | --- |
| Banda, k, chunking, simultaneidade | `src/bioacoustics/config.py` |
| Eventos, limiar, picos | `src/bioacoustics/detection.py` |
| Janelas de 60 s | `src/bioacoustics/pipeline.py` |
| Totais do lote | `reports/campo_resumo.json` |
| Excel provisório (e-mail / tese) | `reports/relatorio_provisorio.xlsx` |
| Como repetir o comando | `docs/REPRODUTIBILIDADE.md` |
| Testes (vento, dueto, chunking, tempos) | `tests/test_detection.py` (`pytest`) |
