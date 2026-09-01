/** Mirrors `parse_recording_datetime` in `src/bioacoustics/audio_io.py`. */
const FILENAME_RE = /R?(\d{8})[-_](\d{6})/i

export function looksLikeRecorderFilename(name: string): boolean {
  const stem = name.replace(/\.[^.]+$/, '')
  const match = FILENAME_RE.exec(stem)
  if (!match) return false
  const [, datePart, timePart] = match
  const year = Number(datePart.slice(0, 4))
  const month = Number(datePart.slice(4, 6))
  const day = Number(datePart.slice(6, 8))
  const hour = Number(timePart.slice(0, 2))
  const minute = Number(timePart.slice(2, 4))
  const second = Number(timePart.slice(4, 6))
  if (month < 1 || month > 12 || day < 1 || day > 31) return false
  if (hour > 23 || minute > 59 || second > 59) return false
  const parsed = new Date(year, month - 1, day, hour, minute, second)
  return (
    parsed.getFullYear() === year &&
    parsed.getMonth() === month - 1 &&
    parsed.getDate() === day
  )
}

export function filenamePatternWarning(name: string): string {
  return (
    `«${name}» não parece seguir o padrão R20241011-180923.WAV. ` +
    'Os gráficos por hora e por mês precisam dessa data no nome. A análise será feita mesmo assim.'
  )
}
