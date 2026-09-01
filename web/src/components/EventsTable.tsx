import { useMemo, useState } from 'react'
import { formatClock, formatHz, formatInteger, formatSeconds } from '@/lib/format'
import type { DetectionReport } from '@/lib/types'

export function EventsTable({ report }: { report: DetectionReport }) {
  const events = report.events
  const total = report.events_sample?.n_total ?? report.summary.n_events
  const isSample = events.length < total
  const [query, setQuery] = useState('')
  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase()
    if (!needle) return events
    return events.filter((event) => event.file.toLowerCase().includes(needle))
  }, [events, query])

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
      <div className="max-h-[28rem] overflow-auto rounded-lg border border-line bg-surface">
        <table className="min-w-full text-left text-sm tabular-nums">
          <thead className="sticky top-0 border-b border-line bg-paper text-muted">
            <tr>
              <th className="px-3 py-2 font-medium">Arquivo</th>
              <th className="px-3 py-2 font-medium">Data</th>
              <th className="px-3 py-2 font-medium">Nº</th>
              <th className="px-3 py-2 font-medium">Início</th>
              <th className="px-3 py-2 font-medium">Fim</th>
              <th className="px-3 py-2 font-medium">Pico</th>
              <th className="px-3 py-2 font-medium">Freq.</th>
              <th className="px-3 py-2 font-medium">Energia</th>
              <th className="px-3 py-2 font-medium">Indiv.</th>
              <th className="px-3 py-2 font-medium">Duração</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((event, index) => (
              <tr key={`${event.file}-${event.event}-${index}`} className="border-b border-line last:border-0">
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
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
