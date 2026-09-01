import type { DetectionReport } from '@/lib/types'

export type ReportSource = 'live' | 'demo' | 'campo'

export type LoadedReport = {
  report: DetectionReport
  source: ReportSource
  spectrogramUrl: (filename: string) => string
}

const CAMPO_REPORT_URL = '/campo/resultado.json'

export function isReport(value: unknown): value is DetectionReport {
  if (!value || typeof value !== 'object') return false
  const report = value as DetectionReport
  return Array.isArray(report.files) && Array.isArray(report.events) && Boolean(report.summary)
}

export function asDetectionReport(value: unknown): DetectionReport {
  if (!isReport(value)) {
    throw new Error('O relatório JSON está em um formato inesperado.')
  }
  return value
}

export function liveSpectrogramUrl(filename: string): string {
  return `/api/spectrograms/${encodeURIComponent(filename)}`
}

export function reportHasSpectrograms(report: DetectionReport, source: ReportSource): boolean {
  if (source === 'campo' || report.has_spectrograms === false) return false
  return report.files.some((file) => Boolean(file.spectrogram))
}

export function inferReportSource(report: DetectionReport, fallback: ReportSource): ReportSource {
  if (report.dashboard_source === 'campo' || report.dashboard_source === 'demo' || report.dashboard_source === 'live') {
    return report.dashboard_source
  }
  if (report.summary.n_files >= 50) return 'campo'
  return fallback
}

export async function loadReport(): Promise<LoadedReport> {
  try {
    const response = await fetch('/api/report')
    if (response.ok) {
      const report = (await response.json()) as DetectionReport
      if (isReport(report) && report.files.length > 0) {
        return {
          report,
          source: 'live',
          spectrogramUrl: (filename) => `/api/spectrograms/${encodeURIComponent(filename)}`,
        }
      }
    }
  } catch {
    // Live API is optional; fall back to the bundled field campaign.
  }

  const response = await fetch(CAMPO_REPORT_URL)
  if (!response.ok) {
    throw new Error('Não foi possível carregar o relatório de detecção.')
  }
  const report = (await response.json()) as DetectionReport
  if (!isReport(report)) {
    throw new Error('O relatório JSON está em um formato inesperado.')
  }
  const source = inferReportSource(report, 'campo')
  return {
    report,
    source,
    spectrogramUrl: (filename) => `/campo/${encodeURIComponent(filename)}`,
  }
}

export async function loadReportFromFile(file: File): Promise<LoadedReport> {
  const text = await file.text()
  const report = JSON.parse(text) as DetectionReport
  if (!isReport(report)) {
    throw new Error('O arquivo não é um resultado.json válido.')
  }
  const source = inferReportSource(report, 'demo')
  return {
    report,
    source,
    spectrogramUrl: (filename) =>
      source === 'campo' ? `/campo/${encodeURIComponent(filename)}` : `/demo/${encodeURIComponent(filename)}`,
  }
}
