import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...parts: ClassValue[]) {
  return twMerge(clsx(parts))
}

export function formatInteger(value: number): string {
  return new Intl.NumberFormat('pt-BR').format(value)
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  const kb = bytes / 1024
  if (kb < 1024) return `${kb.toFixed(1)} KB`
  const mb = bytes / (1024 * 1024)
  if (mb < 1024) return `${mb.toFixed(1)} MB`
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`
}

export function formatHz(hz: number): string {
  return `${new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 1 }).format(hz)} Hz`
}

export function formatClock(iso: string | null): string {
  if (!iso) return 'sem data'
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  return new Intl.DateTimeFormat('pt-BR', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}

export function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds.toFixed(0)} s`
  const minutes = seconds / 60
  if (minutes < 60) return `${minutes.toFixed(1)} min`
  return `${(minutes / 60).toFixed(1)} h`
}

export function formatSeconds(seconds: number): string {
  return `${seconds.toFixed(2)} s`
}

export function monthLabel(month: number): string {
  return new Intl.DateTimeFormat('pt-BR', { month: 'short' })
    .format(new Date(2024, month - 1, 1))
    .replace('.', '')
}

export function hourLabel(hour: number): string {
  return `${String(hour).padStart(2, '0')}h`
}
