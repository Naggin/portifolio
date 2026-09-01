import { DEFAULT_LIMITS, parseLimits, type UploadLimits } from '@/lib/limits'
import { asDetectionReport } from '@/lib/report'
import type { DetectionReport } from '@/lib/types'

export class AnalyzeOfflineError extends Error {
  constructor(
    message = 'O servidor de análise está offline. Não foi possível enviar as gravações.',
  ) {
    super(message)
    this.name = 'AnalyzeOfflineError'
  }
}

export async function loadLimits(): Promise<UploadLimits> {
  try {
    const response = await fetch('/api/limits')
    if (!response.ok) return DEFAULT_LIMITS
    return parseLimits(await response.json())
  } catch {
    return DEFAULT_LIMITS
  }
}

export async function analyzeFiles(files: File[]): Promise<DetectionReport> {
  const body = new FormData()
  for (const file of files) {
    body.append('files', file)
  }

  let response: Response
  try {
    response = await fetch('/api/analyze', { method: 'POST', body })
  } catch {
    throw new AnalyzeOfflineError()
  }

  if (isOfflineStatus(response.status)) {
    throw new AnalyzeOfflineError()
  }

  let payload: unknown
  try {
    payload = await response.json()
  } catch {
    if (!response.ok) {
      throw new AnalyzeOfflineError()
    }
    throw new Error('O servidor de análise devolveu uma resposta inválida.')
  }

  if (!response.ok) {
    throw new Error(errorMessage(payload, response.status))
  }

  try {
    return asDetectionReport(payload)
  } catch {
    throw new Error('O servidor devolveu um relatório em formato inesperado.')
  }
}

function isOfflineStatus(status: number): boolean {
  return status === 404 || status === 502 || status === 503 || status === 504
}

function errorMessage(payload: unknown, status: number): string {
  if (payload && typeof payload === 'object' && 'error' in payload) {
    const error = (payload as { error: unknown }).error
    if (typeof error === 'string' && error.trim()) return error
  }
  if (status === 413) {
    return 'O servidor recusou o envio porque o arquivo excede o limite (HTTP 413).'
  }
  if (status === 400) {
    return 'O servidor recusou a análise (HTTP 400).'
  }
  if (status === 500) {
    return 'Erro interno no servidor de análise (HTTP 500).'
  }
  return `Falha na análise (HTTP ${status}).`
}
