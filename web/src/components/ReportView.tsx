import { SummaryCards } from '@/components/SummaryCards'
import { HourMonthCharts } from '@/components/HourMonthCharts'
import { FilesTable } from '@/components/FilesTable'
import { EventsTable } from '@/components/EventsTable'
import { ProvisionalBanner } from '@/components/ProvisionalBanner'
import type { LoadedReport } from '@/lib/report'

export function ReportView({ loaded }: { loaded: LoadedReport }) {
  return (
    <div className="flex flex-col gap-8">
      <ProvisionalBanner report={loaded.report} />
      <SummaryCards report={loaded.report} />
      <HourMonthCharts byHour={loaded.report.by_hour} byMonth={loaded.report.by_month} />
      <FilesTable loaded={loaded} />
      <EventsTable report={loaded.report} />
    </div>
  )
}
