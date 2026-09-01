import type { DetectionReport } from '@/lib/types'

export type ReportSource = 'live' | 'demo'

export type LoadedReport = {
  report: DetectionReport
  source: ReportSource
  spectrogramUrl: (filename: string) => string
}

function isReport(value: unknown): value is DetectionReport {
  if (!value || typeof value !== 'object') return false
  const report = value as DetectionReport
  return Array.isArray(report.files) && Array.isArray(report.events) && Boolean(report.summary)
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
    // Live API is optional; fall back to the bundled demo.
  }

  const response = await fetch('/demo/resultado.json')
  if (!response.ok) {
    throw new Error('Não foi possível carregar o relatório de detecção.')
  }
  const report = (await response.json()) as DetectionReport
  if (!isReport(report)) {
    throw new Error('O relatório JSON está em um formato inesperado.')
  }
  return {
    report,
    source: 'demo',
    spectrogramUrl: (filename) => `/demo/${encodeURIComponent(filename)}`,
  }
}

export async function loadReportFromFile(file: File): Promise<LoadedReport> {
  const text = await file.text()
  const report = JSON.parse(text) as DetectionReport
  if (!isReport(report)) {
    throw new Error('O arquivo não é um resultado.json válido.')
  }
  return {
    report,
    source: 'demo',
    spectrogramUrl: (filename) => `/demo/${encodeURIComponent(filename)}`,
  }
}
