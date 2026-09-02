import { useEffect, useMemo, useState } from 'react'
import { Loader2 } from 'lucide-react'
import { AUDIO_MISSING_MESSAGE, fetchEventSpectrogram } from '@/lib/eventSpectrogram'
import { formatClock, formatHz, formatInteger, formatSeconds } from '@/lib/format'
import type { DetectionReport, ReportEvent } from '@/lib/types'

const COLUMNS = [
  { key: 'file', label: 'Arquivo', title: 'Nome da gravação' },
  { key: 'recorded_at', label: 'Gravado em', title: 'Data/hora do início do arquivo (nome RYYYYMMDD-HHMMSS)' },
  { key: 'event', label: 'Nº', title: 'Ordem do evento dentro deste arquivo' },
  { key: 'start_s', label: 'Início', title: 'Segundo em que o evento começa no arquivo' },
  { key: 'end_s', label: 'Fim', title: 'Segundo em que o evento termina no arquivo' },
  { key: 'peak_time_s', label: 'Pico', title: 'Instante do pico de energia dentro do evento' },
  { key: 'peak_freq_hz', label: 'Freq.', title: 'Frequência do pico (Hz) na banda calibrada' },
  { key: 'energy', label: 'Energia', title: 'Energia relativa no pico' },
  {
    key: 'n_callers',
    label: 'Indiv.',
    title: 'Picos simultâneos estimados — não é ID de animal (máx. ~2 por limite da banda)',
  },
  { key: 'duration_s', label: 'Duração', title: 'Duração do evento em segundos' },
  {
    key: 'spectrogram',
    label: 'Espectrograma',
    title: 'Gera PNG sob pedido via API (não são 149 962 imagens no Git)',
  },
] as const

function eventRowKey(event: ReportEvent, index: number): string {
  return `${event.file}-${event.event}-${index}`
}

export function EventsTable({ report }: { report: DetectionReport }) {
  const events = report.events
  const total = report.events_sample?.n_total ?? report.summary.n_events
  const isSample = events.length < total
  const [query, setQuery] = useState('')
  const [openKey, setOpenKey] = useState<string | null>(null)
  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase()
    if (!needle) return events
    return events.filter((event) => event.file.toLowerCase().includes(needle))
  }, [events, query])
  const openEvent = useMemo(() => {
    if (!openKey) return null
    return filtered.find((event, index) => eventRowKey(event, index) === openKey) ?? null
  }, [filtered, openKey])

  return (
    <section aria-labelledby="events-heading">
      <div className="mb-3 flex flex-wrap items-end justify-between gap-3">
        <h2 id="events-heading" className="text-base font-medium text-ink">
          Eventos ({formatInteger(isSample ? total : filtered.length)}
          {isSample ? `, amostra de ${formatInteger(filtered.length)}` : ''})
        </h2>
        <label className="text-sm text-muted">
          Filtrar arquivo
          <input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="nome do WAV…"
            className="ml-2 rounded border border-line bg-surface px-2 py-1 text-ink outline-none focus-visible:ring-2 focus-visible:ring-accent/30"
          />
        </label>
      </div>
      {isSample ? (
        <p className="mb-3 text-sm text-muted">
          A tabela mostra uma amostra ({formatInteger(events.length)} de {formatInteger(total)}
          {report.events_sample ? `, ${report.events_sample.per_file} por arquivo` : ''}); o Excel
          tem todos.
        </p>
      ) : null}
      <p className="mb-3 text-sm text-muted">
        <strong className="font-medium text-ink">Ver espectrograma</strong> gera, sob pedido, a
        captura desta linha (áudio local; não são 149&nbsp;962 PNG no Git). A marca verde é o{' '}
        <strong className="font-medium text-ink">Pico</strong> da tabela, não uma re-detecção.{' '}
        <em>Indiv.</em> = cantores simultâneos estimados, não um animal etiquetado. Se a API
        estiver desligada, use os{' '}
        <a href="/espectrogramas/" className="text-accent hover:underline">
          espectrogramas de validação
        </a>{' '}
        (recorte 30:45), não como imagem de cada linha.
      </p>
      {filtered.length === 0 ? (
        <p className="rounded-lg border border-line bg-surface px-4 py-6 text-center text-sm text-muted">
          Nenhum evento corresponde ao filtro. Limpe a busca ou carregue outro relatório.
        </p>
      ) : (
        <div className="max-h-[28rem] overflow-auto rounded-lg border border-line bg-surface">
          <table className="min-w-full text-left text-sm tabular-nums">
            <thead className="sticky top-0 border-b border-line bg-paper text-muted">
              <tr>
                {COLUMNS.map((column) => (
                  <th
                    key={column.key}
                    className="px-3 py-2 font-medium"
                    title={column.title}
                    scope="col"
                  >
                    {column.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filtered.map((event, index) => {
                const rowKey = eventRowKey(event, index)
                const expanded = openKey === rowKey
                return (
                  <tr
                    key={rowKey}
                    className={`border-b border-line last:border-0 ${expanded ? 'bg-accent-soft' : ''}`}
                  >
                    <td className="px-3 py-2 text-ink">{event.file}</td>
                    <td className="px-3 py-2 text-muted">{formatClock(event.recorded_at)}</td>
                    <td className="px-3 py-2">{event.event}</td>
                    <td className="px-3 py-2">{formatSeconds(event.start_s)}</td>
                    <td className="px-3 py-2">{formatSeconds(event.end_s)}</td>
                    <td className="px-3 py-2">{formatSeconds(event.peak_time_s)}</td>
                    <td className="px-3 py-2">{formatHz(event.peak_freq_hz)}</td>
                    <td className="px-3 py-2">{event.energy.toFixed(3)}</td>
                    <td className="px-3 py-2">{event.n_callers}</td>
                    <td className="px-3 py-2">{formatSeconds(event.duration_s)}</td>
                    <td className="px-3 py-2">
                      <button
                        type="button"
                        className="text-accent underline-offset-2 hover:underline"
                        aria-expanded={expanded}
                        aria-controls="event-spectrogram-panel"
                        aria-label={`Ver espectrograma do evento ${event.event} de ${event.file}`}
                        onClick={() => setOpenKey(expanded ? null : rowKey)}
                      >
                        {expanded ? 'Ocultar' : 'Ver espectrograma'}
                      </button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
      {openEvent ? (
        <div id="event-spectrogram-panel" className="mt-3 rounded-lg border border-line bg-surface px-3 py-3">
          <EventSpectrogramPanel event={openEvent} />
        </div>
      ) : null}
    </section>
  )
}

function EventSpectrogramPanel({ event }: { event: ReportEvent }) {
  const [src, setSrc] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [apiDown, setApiDown] = useState(false)
  const [loading, setLoading] = useState(true)
  const requestKey = [
    event.file,
    event.event,
    event.start_s,
    event.end_s,
    event.peak_time_s,
    event.peak_freq_hz,
    event.n_callers,
  ].join('|')

  useEffect(() => {
    const controller = new AbortController()
    let objectUrl: string | null = null
    setLoading(true)
    setError(null)
    setApiDown(false)
    setSrc(null)

    void fetchEventSpectrogram(event, controller.signal)
      .then((result) => {
        if (controller.signal.aborted) return
        if (result.ok) {
          objectUrl = result.objectUrl
          setSrc(result.objectUrl)
          return
        }
        setApiDown(Boolean(result.apiDown))
        setError(result.message)
      })
      .catch((caught: unknown) => {
        if (caught instanceof DOMException && caught.name === 'AbortError') return
        setError(AUDIO_MISSING_MESSAGE)
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false)
      })

    return () => {
      controller.abort()
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [requestKey, event])

  const caption = `${event.file} — evento ${event.event} — pico ${formatSeconds(event.peak_time_s)}, ${formatHz(event.peak_freq_hz)}`

  return (
    <figure className="max-w-4xl">
      {loading ? (
        <p className="inline-flex items-center gap-2 text-sm text-accent" role="status">
          <Loader2 className="size-4 animate-spin" aria-hidden="true" />
          A gerar o espectrograma desta captura…
        </p>
      ) : null}
      {error ? (
        <div
          className="rounded border border-danger/30 bg-danger-soft px-3 py-2 text-sm text-danger"
          role="alert"
        >
          <p>{error}</p>
          {apiDown ? (
            <p className="mt-1">
              <a href="/espectrogramas/" className="underline underline-offset-2">
                Abrir espectrogramas de validação (30:45)
              </a>
            </p>
          ) : null}
        </div>
      ) : null}
      {src ? (
        <img
          src={src}
          alt={caption}
          className="mt-1 w-full rounded border border-line bg-paper object-contain"
        />
      ) : null}
      <figcaption className="mt-2 text-sm text-muted">
        {event.file} — evento {event.event} — pico {formatSeconds(event.peak_time_s)},{' '}
        {formatHz(event.peak_freq_hz)}. cantores simultâneos estimados: {event.n_callers}. A marca
        verde (linha + círculo) é o <span className="text-ink">Pico</span> desta linha da tabela, não
        identidade da espécie.
      </figcaption>
    </figure>
  )
}
