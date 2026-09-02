import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { hourLabel, monthLabel } from '@/lib/format'
import type { HourBucket, MonthBucket } from '@/lib/types'

type ChartRow = {
  label: string
  n_events: number
  note?: string
  kind?: 'peak' | 'zero' | 'missing' | 'normal'
}

const PEAK_HOURS = new Set([4, 5])
const ZERO_HOURS = new Set([11, 12, 13])
const MISSING_MONTHS = new Set([8, 9])

function barColor(kind: ChartRow['kind']): string {
  switch (kind) {
    case 'peak':
      return 'var(--color-accent)'
    case 'zero':
      return 'var(--color-line)'
    case 'missing':
      return 'var(--color-warn-soft)'
    default:
      return 'var(--color-accent)'
  }
}

function completeHours(buckets: HourBucket[]): ChartRow[] {
  const map = new Map(buckets.map((bucket) => [bucket.hour, bucket.n_events]))
  return Array.from({ length: 24 }, (_, hour) => {
    const n_events = map.get(hour) ?? 0
    let note = ''
    let kind: ChartRow['kind'] = 'normal'
    if (PEAK_HOURS.has(hour)) {
      note = 'Pico: mais arquivos começam neste bloco (4–5 h)'
      kind = 'peak'
    } else if (ZERO_HOURS.has(hour)) {
      note = 'Zero = nenhum WAV começa nesta hora (não é «zero canto»)'
      kind = 'zero'
    } else if (n_events === 0) {
      note = 'Sem arquivos com data no nome nesta hora'
      kind = 'zero'
    }
    return { label: hourLabel(hour), n_events, note, kind }
  })
}

function completeMonths(buckets: MonthBucket[]): ChartRow[] {
  const map = new Map(buckets.map((bucket) => [bucket.month, bucket.n_events]))
  return Array.from({ length: 12 }, (_, index) => {
    const month = index + 1
    const n_events = map.get(month) ?? 0
    let note = ''
    let kind: ChartRow['kind'] = 'normal'
    if (MISSING_MONTHS.has(month)) {
      note = 'MP3s sem data no nome — eventos existem no total, mas não entram aqui'
      kind = 'missing'
    } else if (n_events === 0) {
      note = 'Sem WAV com data neste mês'
      kind = 'zero'
    } else if (month === 10) {
      note = 'Pico entre arquivos com data no nome'
      kind = 'peak'
    }
    return { label: monthLabel(month), n_events, note, kind }
  })
}

export function HourMonthCharts({
  byHour,
  byMonth,
}: {
  byHour: HourBucket[]
  byMonth: MonthBucket[]
}) {
  const hours = completeHours(byHour)
  const months = completeMonths(byMonth)
  const peakHour = hours.reduce((best, row) => (row.n_events > best.n_events ? row : best))

  return (
    <section className="grid gap-6 lg:grid-cols-2" aria-label="Agregados temporais">
      <ChartCard
        title="Eventos por hora (início da gravação)"
        subtitle="A hora vem do nome do arquivo (RYYYYMMDD-HHMMSS), não do relógio de cada canto. MP3s sem data no nome ficam de fora."
        data={hours}
        peakLabel={
          peakHour.n_events > 0
            ? `Pico: ${peakHour.label} (${peakHour.n_events.toLocaleString('pt-BR')} eventos)`
            : undefined
        }
      />
      <ChartCard
        title="Eventos por mês (início da gravação)"
        subtitle="Mês = data no nome do arquivo. Agosto e setembro podem ficar vazios por MP3s sem data — os eventos entram no total do Resumo."
        data={months}
      />
    </section>
  )
}

function ChartCard({
  title,
  subtitle,
  data,
  peakLabel,
}: {
  title: string
  subtitle: string
  data: ChartRow[]
  peakLabel?: string
}) {
  return (
    <div className="rounded-lg border border-line bg-surface p-4">
      <h2 className="text-base font-medium text-ink">{title}</h2>
      <p className="mt-1 text-xs leading-snug text-muted">{subtitle}</p>
      {peakLabel ? (
        <p className="mt-2 text-xs font-medium text-accent">{peakLabel}</p>
      ) : null}
      <div className="mt-3 h-56 sm:h-64">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 16, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid stroke="var(--color-line)" vertical={false} />
            <XAxis
              dataKey="label"
              tick={{ fill: 'var(--color-muted)', fontSize: 10 }}
              interval={2}
            />
            <YAxis
              allowDecimals={false}
              tick={{ fill: 'var(--color-muted)', fontSize: 11 }}
              width={44}
              tickFormatter={(value: number) => value.toLocaleString('pt-BR')}
            />
            <Tooltip
              formatter={(value) => [Number(value ?? 0).toLocaleString('pt-BR'), 'Eventos']}
              labelFormatter={(label, payload) => {
                const row = payload?.[0]?.payload as ChartRow | undefined
                return row?.note ? `${label} — ${row.note}` : String(label)
              }}
              contentStyle={{
                background: 'var(--color-paper)',
                border: '1px solid var(--color-line)',
                fontSize: 12,
                maxWidth: 280,
              }}
            />
            <ReferenceLine y={0} stroke="var(--color-line)" />
            <Bar dataKey="n_events" radius={[2, 2, 0, 0]} maxBarSize={20}>
              {data.map((row) => (
                <Cell key={row.label} fill={barColor(row.kind)} />
              ))}
              <LabelList
                dataKey="n_events"
                position="top"
                formatter={(value: unknown) => {
                  const num = typeof value === 'number' ? value : Number(value)
                  if (!Number.isFinite(num) || num <= 0) return ''
                  const isPeak = data.some((row) => row.n_events === num && row.kind === 'peak')
                  return isPeak ? num.toLocaleString('pt-BR') : ''
                }}
                style={{ fill: 'var(--color-ink)', fontSize: 10 }}
              />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
