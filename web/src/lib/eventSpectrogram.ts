import type { ReportEvent } from '@/lib/types'

export const AUDIO_MISSING_MESSAGE = 'Áudio deste ficheiro não está nesta máquina.'
export const API_DOWN_MESSAGE =
  'Não foi possível gerar o espectrograma (API desligada). Os três PNG de validação da madrugada estão na galeria — não representam cada linha desta tabela.'

export function eventSpectrogramUrl(event: ReportEvent): string {
  const params = new URLSearchParams({
    file: event.file,
    start_s: String(event.start_s),
    end_s: String(event.end_s),
    peak_time_s: String(event.peak_time_s),
    peak_freq_hz: String(event.peak_freq_hz),
    n_callers: String(event.n_callers),
    event: String(event.event),
  })
  return `/api/event-spectrogram?${params.toString()}`
}

export type EventSpectrogramResult =
  | { ok: true; objectUrl: string }
  | { ok: false; message: string; apiDown?: boolean }

function errorFromPayload(payload: unknown, fallback: string): string {
  if (payload && typeof payload === 'object') {
    const record = payload as { error?: unknown; code?: unknown }
    if (record.code === 'audio_not_found') return AUDIO_MISSING_MESSAGE
    if (typeof record.error === 'string' && record.error.trim()) {
      if (record.error.includes('não está nesta máquina')) return AUDIO_MISSING_MESSAGE
      return record.error
    }
  }
  return fallback
}

export async function fetchEventSpectrogram(
  event: ReportEvent,
  signal?: AbortSignal,
): Promise<EventSpectrogramResult> {
  let response: Response
  try {
    response = await fetch(eventSpectrogramUrl(event), { signal })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    return { ok: false, message: API_DOWN_MESSAGE, apiDown: true }
  }

  if (response.status === 404) {
    let payload: unknown = null
    try {
      payload = await response.json()
    } catch {
      payload = null
    }
    return { ok: false, message: errorFromPayload(payload, AUDIO_MISSING_MESSAGE) }
  }

  if (response.status === 502 || response.status === 503 || response.status === 504) {
    return { ok: false, message: API_DOWN_MESSAGE, apiDown: true }
  }

  if (!response.ok) {
    let payload: unknown = null
    try {
      payload = await response.json()
    } catch {
      payload = null
    }
    return {
      ok: false,
      message: errorFromPayload(payload, `Falha ao gerar o espectrograma (HTTP ${response.status}).`),
    }
  }

  const blob = await response.blob()
  if (!blob.size) {
    return { ok: false, message: 'O servidor devolveu uma imagem vazia.' }
  }
  return { ok: true, objectUrl: URL.createObjectURL(blob) }
}
