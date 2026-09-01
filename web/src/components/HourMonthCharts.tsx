import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { hourLabel, monthLabel } from '@/lib/format'
import type { HourBucket, MonthBucket } from '@/lib/types'

type ChartRow = { label: string; n_events: number }

function completeHours(buckets: HourBucket[]): ChartRow[] {
  const map = new Map(buckets.map((bucket) => [bucket.hour, bucket.n_events]))
  return Array.from({ length: 24 }, (_, hour) => ({
    label: hourLabel(hour),
    n_events: map.get(hour) ?? 0,
  }))
}

function completeMonths(buckets: MonthBucket[]): ChartRow[] {
  const map = new Map(buckets.map((bucket) => [bucket.month, bucket.n_events]))
  return Array.from({ length: 12 }, (_, index) => {
    const month = index + 1
    return {
      label: monthLabel(month),
      n_events: map.get(month) ?? 0,
    }
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

  return (
    <section className="grid gap-6 lg:grid-cols-2" aria-label="Agregados temporais">
      <ChartCard title="Eventos por hora" data={hours} />
      <ChartCard title="Eventos por mês" data={months} />
    </section>
  )
}

function ChartCard({ title, data }: { title: string; data: ChartRow[] }) {
  return (
    <div className="rounded-lg border border-line bg-surface p-4">
      <h2 className="mb-3 text-base font-medium text-ink">{title}</h2>
      <div className="h-56">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid stroke="var(--color-line)" vertical={false} />
            <XAxis dataKey="label" tick={{ fill: 'var(--color-muted)', fontSize: 11 }} interval={2} />
            <YAxis
              allowDecimals={false}
              tick={{ fill: 'var(--color-muted)', fontSize: 11 }}
              width={36}
            />
            <Tooltip
              formatter={(value) => [String(value ?? 0), 'Eventos']}
              contentStyle={{
                background: 'var(--color-paper)',
                border: '1px solid var(--color-line)',
                fontSize: 13,
              }}
            />
            <Bar dataKey="n_events" fill="var(--color-accent)" radius={[2, 2, 0, 0]} maxBarSize={18} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
