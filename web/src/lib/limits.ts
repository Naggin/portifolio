/** Client-side upload limiter. Keep values obvious; `/api/limits` may override at runtime. */

export const MAX_FILES = 10
export const MAX_BYTES = 500 * 1024 * 1024
export const ALLOWED_EXTENSIONS = ['.wav', '.flac', '.ogg', '.mp3'] as const

export type UploadLimits = {
  max_files: number
  max_bytes: number
  extensions: string[]
}

export const DEFAULT_LIMITS: UploadLimits = {
  max_files: MAX_FILES,
  max_bytes: MAX_BYTES,
  extensions: [...ALLOWED_EXTENSIONS],
}

export type FileLike = {
  name: string
  size: number
}

export type FileRejection = {
  code: 'empty' | 'oversize' | 'extension' | 'too_many'
  message: string
}

const DOT_EXT = /\.([^.]+)$/

export function fileExtension(name: string): string {
  const match = DOT_EXT.exec(name)
  return match ? `.${match[1].toLowerCase()}` : ''
}

export function normalizeExtensions(values: unknown): string[] {
  if (!Array.isArray(values)) return [...ALLOWED_EXTENSIONS]
  const normalized = values
    .filter((value): value is string => typeof value === 'string' && value.length > 0)
    .map((value) => (value.startsWith('.') ? value.toLowerCase() : `.${value.toLowerCase()}`))
  return normalized.length > 0 ? normalized : [...ALLOWED_EXTENSIONS]
}

export function parseLimits(value: unknown): UploadLimits {
  if (!value || typeof value !== 'object') return DEFAULT_LIMITS
  const raw = value as Record<string, unknown>
  const maxFiles = Number(raw.max_files)
  const maxBytes = Number(raw.max_bytes)
  return {
    max_files: Number.isFinite(maxFiles) && maxFiles > 0 ? maxFiles : MAX_FILES,
    max_bytes: Number.isFinite(maxBytes) && maxBytes > 0 ? maxBytes : MAX_BYTES,
    extensions: normalizeExtensions(raw.extensions),
  }
}

export function oversizeMessage(name: string, size: number, maxBytes: number): string {
  return (
    `«${name}» tem ${formatBytesPt(size)}, acima do limite de ${formatBytesPt(maxBytes)}. ` +
    'O painel analisa gravações de até 500 MB (~1 hora em WAV típico). ' +
    'Arquivos maiores devem aguardar o processamento em partes.'
  )
}

export function rejectFile(file: FileLike, limits: UploadLimits): FileRejection | null {
  const ext = fileExtension(file.name)
  if (!ext || !limits.extensions.includes(ext)) {
    const accepted = limits.extensions.map((item) => item.replace('.', '').toUpperCase()).join(', ')
    return {
      code: 'extension',
      message: `«${file.name}» não é um formato aceito. Use ${accepted}.`,
    }
  }
  if (file.size <= 0) {
    return {
      code: 'empty',
      message: `«${file.name}» está vazio (0 bytes) e não pode ser analisado.`,
    }
  }
  if (file.size > limits.max_bytes) {
    return {
      code: 'oversize',
      message: oversizeMessage(file.name, file.size, limits.max_bytes),
    }
  }
  return null
}

export type QueuedAudio = {
  file: File
  rejection: FileRejection | null
}

export function queueAudioFiles(files: File[], limits: UploadLimits): QueuedAudio[] {
  return files.map((file, index) => {
    if (index >= limits.max_files) {
      return {
        file,
        rejection: {
          code: 'too_many',
          message: `No máximo ${limits.max_files} arquivos por lote. «${file.name}» não foi enviado.`,
        },
      }
    }
    return { file, rejection: rejectFile(file, limits) }
  })
}

function formatBytesPt(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  const kb = bytes / 1024
  if (kb < 1024) return `${kb.toFixed(1)} KB`
  const mb = bytes / (1024 * 1024)
  if (mb < 1024) return `${mb.toFixed(1)} MB`
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`
}
