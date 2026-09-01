import { useId, useState, type DragEvent } from 'react'
import { Upload } from 'lucide-react'
import { cn } from '@/lib/format'
import type { UploadLimits } from '@/lib/limits'

type DropZoneProps = {
  disabled?: boolean
  limits: UploadLimits
  onFiles: (files: File[]) => void
}

export function DropZone({ disabled = false, limits, onFiles }: DropZoneProps) {
  const inputId = useId()
  const accept = limits.extensions.join(',')
  const formats = limits.extensions.map((ext) => ext.replace('.', '').toUpperCase()).join(', ')
  const maxMb = (limits.max_bytes / (1024 * 1024)).toFixed(0)
  const [dragging, setDragging] = useState(false)

  function takeFiles(list: FileList | null) {
    if (!list || list.length === 0) return
    onFiles(Array.from(list))
  }

  function onDrop(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault()
    setDragging(false)
    if (disabled) return
    takeFiles(event.dataTransfer.files)
  }

  function onDragOver(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault()
    event.dataTransfer.dropEffect = 'copy'
  }

  return (
    <label
      htmlFor={disabled ? undefined : inputId}
      onDrop={onDrop}
      onDragOver={onDragOver}
      onDragEnter={(event) => {
        event.preventDefault()
        if (!disabled) setDragging(true)
      }}
      onDragLeave={() => setDragging(false)}
      className={cn(
        'block cursor-pointer rounded-lg border-2 border-dashed border-line bg-surface px-6 py-10 text-center',
        'has-[:focus-visible]:border-accent has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-accent/30',
        dragging && 'border-accent bg-accent-soft',
        disabled && 'cursor-not-allowed opacity-60',
      )}
    >
      <input
        id={inputId}
        type="file"
        multiple
        accept={accept}
        disabled={disabled}
        className="sr-only"
        aria-label="Selecionar gravações de áudio"
        onChange={(event) => {
          takeFiles(event.target.files)
          event.target.value = ''
        }}
      />
      <Upload className="mx-auto mb-3 size-8 text-accent" aria-hidden="true" />
      <p className="text-lg font-medium text-ink">Arraste as gravações aqui</p>
      <p className="mt-1 text-sm text-muted">
        ou escolha no seletor ({formats}; até {limits.max_files} por lote, {maxMb} MB cada)
      </p>
      <span className="mt-4 inline-block rounded border border-line bg-paper px-3 py-1.5 text-sm font-medium text-ink">
        Selecionar arquivos
      </span>
    </label>
  )
}
