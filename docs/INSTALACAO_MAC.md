# Instalação no macOS

Guia para montar o ambiente **neste notebook Mac**, a fim de analisar os áudios de campo e gerar o Excel. O painel web é opcional.

Os requisitos de software são os mesmos de `docs/REPRODUTIBILIDADE.md`: **Python 3.11+** e **ffmpeg**. A versão recomendada no Homebrew é a 3.12.

No Linux ou no Windows, o equivalente está no `README.md` da raiz.

## O que instalar (dois níveis)

| Nível | Para quê | Obrigatório? |
| --- | --- | --- |
| **1. Pipeline Python** | Detectar vocalizações e gravar `output/resultado.xlsx` + `output/resultado.json` | **Sim**, se o objetivo é analisar áudio e gerar a planilha da tese |
| **2. Dashboard React** | Ver `resultado.json` no navegador (gráficos e tabelas) | Não. O Excel já basta para tabelas; o painel só visualiza |

Não é preciso enviar os ~18 GB do Drive para o GitHub. O repositório contém o código; o áudio fica **só no disco local**.

## 1. Ferramentas de sistema

### 1.1 Command Line Tools (Xcode)

Se o `pip` ou a compilação do `ffmpeg` reclamarem de compilador (`xcrun`, `clang`, `SDK`):

```bash
xcode-select --install
```

Aceite a janela do sistema e espere terminar. Sem isso, pacotes que compilem extensões nativas (às vezes `numpy`/`llvmlite`) falham.

### 1.2 Homebrew

Se `brew` ainda não existir:

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

No Apple Silicon (M1/M2/M3), o Homebrew fica em `/opt/homebrew`. No Intel, em `/usr/local`. Se o terminal não achar o `brew` depois da instalação, no Apple Silicon:

```bash
echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zprofile
eval "$(/opt/homebrew/bin/brew shellenv)"
```

### 1.3 Python 3.12 e ffmpeg

```bash
brew install python@3.12 ffmpeg
```

`ffmpeg` é **obrigatório** para `.m4a` (referência de calibração) e para vários formatos de campo. O `librosa`/`soundfile` usam-no para decodificar e para ler arquivos longos por fatias, sem carregar a gravação inteira.

Confirme:

```bash
python3 --version    # 3.11 ou 3.12
ffmpeg -version
which python3
```

O `python3` deve apontar para o Homebrew (`/opt/homebrew/bin/python3` no Apple Silicon, `/usr/local/bin/python3` no Intel), não para um Python antigo do sistema.

## 2. Apple Silicon versus Intel

Prefira as **wheels oficiais** do PyPI (`pip install -r requirements.txt` no Python do Homebrew). Não instale Anaconda/Miniconda a menos que o `pip` falhe de forma persistente: misturar conda e Homebrew costuma gerar `numpy`/`llvmlite` incompatíveis com o `librosa`.

Se `numpy`, `llvmlite` ou `librosa` falharem na instalação:

1. Confirme a arquitetura:

   ```bash
   arch
   python3 -c "import platform; print(platform.machine())"
   ```

   No M1/M2/M3 os dois devem ser `arm64`. No Intel, `x86_64`. Se o Python for `x86_64` num Mac ARM, o terminal está em Rosetta — feche, abra o Terminal nativo e use o `python3` do Homebrew.

2. Recrie o ambiente virtual (sec. 4) com esse Python. Não misture um `.venv` criado sob Rosetta com pacotes `arm64`.

## 3. Código (clone)

Na pasta em que quiser o projeto (por exemplo `~/Documents`):

```bash
git clone https://github.com/Naggin/portifolio.git
cd portifolio
```

Não copie o Drive inteiro para dentro do repositório no GitHub. Só o clone do código.

## 4. Pipeline Python (obrigatório)

Na raiz do repositório:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

O prompt passa a mostrar `(.venv)`. Sempre ative o ambiente antes de detectar:

```bash
source .venv/bin/activate
```

### 4.1 Teste sem áudio de campo

O gerador sintético produz um WAV curto (canto solo, dueto e vento) com data no nome, no padrão do gravador:

```bash
python src/generate_sample.py
PYTHONPATH=src python src/detect.py data/audios/R20241011-180923.WAV
```

Saída em `output/` (pasta ignorada pelo Git):

- `output/resultado.xlsx` — planilha (abas Events, Files, By hour, By month)
- `output/resultado.json` — o mesmo conteúdo para o painel
- `output/<arquivo>_spectrogram.png` — conferência humana (omitir com `--no-spectrogram`)

Pasta inteira:

```bash
PYTHONPATH=src python src/detect.py data/audios/
```

Cópia local do Drive (gravações de horas; sem PNG, mais rápido):

```bash
PYTHONPATH=src python src/detect.py data/field --no-spectrogram
```

O Excel e o JSON **só são gravados quando o lote termina**. Enquanto `detect.py` estiver rodando, não use totais do log como resultado de tese.

Bandeiras úteis: `--lowcut` / `--highcut`, `--threshold-k`, `--output-dir`, `--report`, `--json-report`. Detalhe em `docs/REPRODUTIBILIDADE.md`.

## 5. Onde colocar os áudios (Drive local)

| Pasta | Uso | No Git? |
| --- | --- | --- |
| `data/audios/` | Amostras e testes (o gerador sintético escreve aqui) | ignorada (`*.WAV` etc.; fica só `.gitkeep`) |
| `data/field/` | Cópia de trabalho das pastas de açude (WAV ~1 h, MP3 de várias horas) | ignorada; **não commitar** |
| `output/` | `resultado.xlsx`, `resultado.json`, PNG | ignorada |

Fluxo recomendado:

1. No Google Drive, baixe **só as pastas de campo que vai analisar** para o disco do Mac (Finder → Drive).
2. Copie para `data/field/` (mantenha a estrutura das pastas de açude, se quiser).
3. **Não** faça upload desses WAV/MP3 para o GitHub. São dezenas de gigabytes e o `.gitignore` já os exclui.

Pasta de campo a omitir, se existir na cópia: `15/08 açude 2 (esse nao precisa)`.

### Disco e memória (WAV de 1 h / MP3 de 6 h)

O pipeline **não** carrega o arquivo inteiro na RAM: arquivos longos são processados em janelas de 60 s (`chunk_duration_s`; ver `docs/METODOS.md`). Ainda assim é preciso **espaço em disco** para os próprios arquivos e para a saída.

Ordem de grandeza (varia com taxa de amostragem e compressão):

- WAV de ~1 h: frequentemente **centenas de MB a alguns GB por arquivo**;
- MP3 de ~6 h: menor que o WAV equivalente, mas ainda ocupa disco;
- o lote completo no Drive gira em torno de **18 GB** — o notebook precisa de folga além disso (sistema + `output/`).

RAM: um Mac recente costuma bastar para o chunking de 60 s. O gargalo típico é **disco**, não carregar 6 h de áudio de uma vez.

## 6. Dashboard React (opcional)

Só depois de existir `output/resultado.json` (ou para ver o lote de campo em `web/public/campo/`).

Node.js **20 ou superior**:

```bash
brew install node
node -v    # v20, v22, …
```

Dois terminais, na raiz do repositório, com o `.venv` ativo no primeiro:

```bash
# Terminal 1 — API que lê output/resultado.json
source .venv/bin/activate
PYTHONPATH=src python -m bioacoustics.api
# http://127.0.0.1:8000  (GET /api/report)
```

```bash
# Terminal 2 — interface
cd web
npm install          # só na primeira vez
npm run dev
# http://127.0.0.1:5173
```

O Vite encaminha `/api` para `127.0.0.1:8000` (`web/vite.config.ts`). Sem a API, o painel cai no JSON do lote de campo em `web/public/campo/resultado.json` (totais reais; a tabela de eventos é uma amostra).

O upload pelo painel (`POST /api/analyze`) serve para poucos arquivos e **não** substitui o lote CLI em `data/field/`.

Como ler as abas e o JSON: `docs/COMO_LER_OS_RESULTADOS.md`.

## 7. Verificação rápida

Com o venv ativo:

```bash
PYTHONPATH=src pytest -q
```

Se os testes passam e o `generate_sample.py` + `detect.py` geram `output/resultado.xlsx`, o ambiente está utilizável para o lote local.

## 8. Problemas frequentes no Mac

| Sintoma | O que checar |
| --- | --- |
| `ffmpeg: command not found` | `brew install ffmpeg`; novo Terminal depois do brew |
| `ModuleNotFoundError: bioacoustics` | prefixar com `PYTHONPATH=src`; venv ativo |
| Falha ao instalar `llvmlite` / `librosa` | arquitetura `arm64` vs `x86_64` (sec. 2); Python do Homebrew, não Anaconda |
| `xcrun: error` / clang ausente | `xcode-select --install` |
| Painel sem dados de campo | API no ar e `output/resultado.json` já gerado pelo CLI |
| Gatekeeper bloqueia um binário baixado | preferir Homebrew/`pip`; não é necessário desativar o Gatekeeper para este projeto |
