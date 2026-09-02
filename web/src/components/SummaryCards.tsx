import { formatDuration, formatInteger } from '@/lib/format'
import type { DetectionReport } from '@/lib/types'

export function SummaryCards({ report }: { report: DetectionReport }) {
  const items = [
    {
      label: 'Arquivos',
      value: formatInteger(report.summary.n_files),
      subtitle: 'Gravações analisadas neste lote',
    },
    {
      label: 'Eventos',
      value: formatInteger(report.summary.n_events),
      subtitle: 'Picos na banda 2,6–3,2 kHz — não são machos',
    },
    {
      label: 'Máx. simultâneos',
      value: formatInteger(report.summary.max_simultaneous),
      subtitle: 'Picos distintos no mesmo instante (teto ~2)',
    },
    {
      label: 'Duração total',
      value: formatDuration(report.summary.total_duration_s),
      subtitle: 'Soma das gravações processadas',
    },
  ]

  return (
    <section aria-labelledby="summary-heading">
      <h2 id="summary-heading" className="mb-3 text-base font-medium text-ink">
        Resumo
      </h2>
      <ul className="grid grid-cols-1 gap-3 xs:grid-cols-2 sm:grid-cols-2 lg:grid-cols-4">
        {items.map((item) => (
          <li key={item.label} className="rounded-lg border border-line bg-surface px-4 py-3">
            <p className="text-sm text-muted">{item.label}</p>
            <p className="mt-1 font-mono text-xl tabular-nums text-ink">{item.value}</p>
            <p className="mt-1 text-xs leading-snug text-muted">{item.subtitle}</p>
          </li>
        ))}
      </ul>
      <p className="mt-3 text-sm text-muted">
        {report.species} ({report.common_name}) · banda {report.config.lowcut_hz}–
        {report.config.highcut_hz} Hz · limiar k={report.config.threshold_k}
      </p>
    </section>
  )
}
