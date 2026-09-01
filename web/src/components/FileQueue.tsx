import { AlertCircle, CheckCircle2, Clock, Loader2 } from 'lucide-react'
import { cn, formatBytes } from '@/lib/format'

export type FileStatus = 'waiting' | 'sending' | 'done' | 'error'

export type QueueItem = {
  id: string
  name: string
  size: number
  status: FileStatus
  message?: string
}

const STATUS_LABEL: Record<FileStatus, string> = {
  waiting: 'Aguardando',
  sending: 'Enviando',
  done: 'Concluído',
  error: 'Erro',
}

export function FileQueue({ items }: { items: QueueItem[] }) {
  if (items.length === 0) return null

  return (
    <ul className="divide-y divide-line rounded-lg border border-line bg-surface" aria-label="Arquivos selecionados">
      {items.map((item) => (
        <li key={item.id} className="flex flex-col gap-1 px-4 py-3 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0">
            <p className="truncate font-medium text-ink" title={item.name}>
              {item.name}
            </p>
            <p className="text-sm text-muted">{formatBytes(item.size)}</p>
            {item.message ? (
              <p
                className={cn(
                  'mt-1 text-sm',
                  item.status === 'error' ? 'text-danger' : 'text-warn',
                )}
              >
                {item.message}
              </p>
            ) : null}
          </div>
          <StatusBadge status={item.status} />
        </li>
      ))}
    </ul>
  )
}

function StatusBadge({ status }: { status: FileStatus }) {
  const Icon =
    status === 'sending' ? Loader2 : status === 'done' ? CheckCircle2 : status === 'error' ? AlertCircle : Clock

  return (
    <span
      className={cn(
        'inline-flex shrink-0 items-center gap-1.5 self-start rounded-full px-2.5 py-1 text-xs font-medium',
        status === 'waiting' && 'bg-paper text-muted',
        status === 'sending' && 'bg-accent-soft text-accent',
        status === 'done' && 'bg-accent-soft text-accent',
        status === 'error' && 'bg-danger-soft text-danger',
      )}
    >
      <Icon className={cn('size-3.5', status === 'sending' && 'animate-spin')} aria-hidden="true" />
      {STATUS_LABEL[status]}
    </span>
  )
}
