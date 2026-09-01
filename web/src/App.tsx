import { useCallback, useEffect, useId, useState } from 'react'
import { FileJson, Loader2 } from 'lucide-react'
import { DropZone } from '@/components/DropZone'
import { FileQueue, type QueueItem } from '@/components/FileQueue'
import { ReportView } from '@/components/ReportView'
import { AnalyzeOfflineError, analyzeFiles, loadLimits } from '@/lib/analyze'
import { filenamePatternWarning, looksLikeRecorderFilename } from '@/lib/filename'
import { DEFAULT_LIMITS, queueAudioFiles, type UploadLimits } from '@/lib/limits'
import {
  liveSpectrogramUrl,
  loadReport,
  loadReportFromFile,
  type LoadedReport,
  type ReportSource,
} from '@/lib/report'

export default function App() {
  const jsonInputId = useId()
  const [limits, setLimits] = useState<UploadLimits>(DEFAULT_LIMITS)
  const [loaded, setLoaded] = useState<LoadedReport | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [queue, setQueue] = useState<QueueItem[]>([])
  const [analyzing, setAnalyzing] = useState(false)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const [warnings, setWarnings] = useState<string[]>([])

  useEffect(() => {
    let cancelled = false
    void loadLimits().then((next) => {
      if (!cancelled) setLimits(next)
    })
    void loadReport()
      .then((report) => {
        if (!cancelled) setLoaded(report)
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setLoadError(error instanceof Error ? error.message : 'Falha ao carregar o relatório.')
        }
      })
    return () => {
      cancelled = true
    }
  }, [])

  const handleAudio = useCallback(
    async (files: File[]) => {
      if (analyzing || files.length === 0) return

      const queued = queueAudioFiles(files, limits)
      const items: QueueItem[] = queued.map((entry, index) => ({
        id: `${entry.file.name}-${entry.file.size}-${entry.file.lastModified}-${index}`,
        name: entry.file.name,
        size: entry.file.size,
        status: entry.rejection ? 'error' : 'waiting',
        message: entry.rejection?.message,
      }))
      const accepted = queued.filter((entry) => !entry.rejection).map((entry) => entry.file)
      const nameWarnings = accepted
        .filter((file) => !looksLikeRecorderFilename(file.name))
        .map((file) => filenamePatternWarning(file.name))

      setQueue(items)
      setWarnings(nameWarnings)
      setUploadError(null)

      if (accepted.length === 0) return

      setAnalyzing(true)
      setQueue((current) =>
        current.map((item) => (item.status === 'waiting' ? { ...item, status: 'sending' } : item)),
      )

      try {
        const report = await analyzeFiles(accepted)
        const next: LoadedReport = {
          report,
          source: 'live',
          spectrogramUrl: liveSpectrogramUrl,
        }
        setLoaded(next)
        setQueue((current) =>
          current.map((item) => (item.status === 'sending' ? { ...item, status: 'done' } : item)),
        )
      } catch (error) {
        const message =
          error instanceof AnalyzeOfflineError
            ? error.message
            : error instanceof Error
              ? error.message
              : 'Falha ao enviar as gravações.'
        setUploadError(message)
        setQueue((current) =>
          current.map((item) =>
            item.status === 'sending' ? { ...item, status: 'error', message } : item,
          ),
        )
      } finally {
        setAnalyzing(false)
      }
    },
    [analyzing, limits],
  )

  async function handleJson(file: File | undefined) {
    if (!file) return
    setUploadError(null)
    try {
      const report = await loadReportFromFile(file)
      setLoaded(report)
    } catch (error) {
      setUploadError(error instanceof Error ? error.message : 'Não foi possível abrir o JSON.')
    }
  }

  return (
    <div className="flex min-h-svh flex-col">
      <header className="border-b border-line bg-surface px-4 py-5 sm:px-8">
        <p className="text-xs uppercase tracking-wide text-muted">Painel de campo</p>
        <h1 className="mt-1 text-2xl font-medium text-ink">Detecção de vocalizações</h1>
        <p className="mt-1 max-w-2xl text-sm text-muted">
          Envie gravações de <em>Sphaenorhynchus caramaschii</em> (perereca-de-banhado). A contagem
          usa o espectrograma numérico; a imagem serve só para conferência.
        </p>
      </header>

      <main className="flex flex-1 flex-col gap-6 px-4 py-6 sm:px-8" aria-busy={analyzing}>
        <section aria-labelledby="upload-heading" className="flex flex-col gap-3">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h2 id="upload-heading" className="text-base font-medium text-ink">
              Gravações
            </h2>
            <label htmlFor={jsonInputId} className="inline-flex cursor-pointer items-center gap-1.5 text-sm text-accent hover:underline">
              <FileJson className="size-4" aria-hidden="true" />
              Abrir resultado.json
              <input
                id={jsonInputId}
                type="file"
                accept=".json,application/json"
                className="sr-only"
                onChange={(event) => {
                  void handleJson(event.target.files?.[0])
                  event.target.value = ''
                }}
              />
            </label>
          </div>
          <DropZone disabled={analyzing} limits={limits} onFiles={(files) => void handleAudio(files)} />
          {analyzing ? (
            <p className="inline-flex items-center gap-2 text-sm text-accent" role="status">
              <Loader2 className="size-4 animate-spin" aria-hidden="true" />
              Analisando gravações… isso pode levar alguns minutos mesmo para arquivos curtos.
            </p>
          ) : null}
          <div aria-live="polite" className="flex flex-col gap-2">
            {warnings.map((warning) => (
              <p key={warning} className="rounded border border-warn/30 bg-warn-soft px-3 py-2 text-sm text-warn">
                {warning}
              </p>
            ))}
            {uploadError ? (
              <p className="rounded border border-danger/30 bg-danger-soft px-3 py-2 text-sm text-danger">
                {uploadError}
              </p>
            ) : null}
          </div>
          <FileQueue items={queue} />
        </section>

        {loadError && !loaded ? (
          <p className="text-sm text-danger">{loadError}</p>
        ) : null}

        {loaded ? (
          <section className="flex flex-col gap-4">
            <SourceBanner source={loaded.source} />
            <ReportView loaded={loaded} />
          </section>
        ) : !loadError ? (
          <p className="text-sm text-muted">Carregando o relatório de campo…</p>
        ) : null}
      </main>
    </div>
  )
}

function SourceBanner({ source }: { source: ReportSource }) {
  if (source === 'campo') {
    return (
      <p className="rounded border border-line bg-surface px-3 py-2 text-sm text-muted">
        Exibindo o lote de campo (Drive). Suba a API para reanalisar gravações.
      </p>
    )
  }
  if (source === 'demo') {
    return (
      <p className="rounded border border-line bg-surface px-3 py-2 text-sm text-muted">
        Exibindo um relatório de demonstração. O servidor de análise não está disponível ou ainda
        não gerou um resultado — envie gravações quando a API estiver no ar.
      </p>
    )
  }
  return (
    <p className="rounded border border-accent/30 bg-accent-soft px-3 py-2 text-sm text-accent">
      Relatório ao vivo do servidor de análise.
    </p>
  )
}
