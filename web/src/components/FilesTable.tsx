import { useState } from 'react'
import { formatClock, formatDuration, formatInteger } from '@/lib/format'
import { reportHasSpectrograms, type LoadedReport } from '@/lib/report'

export function FilesTable({ loaded }: { loaded: LoadedReport }) {
  const [open, setOpen] = useState<string | null>(null)
  const showSpectrograms = reportHasSpectrograms(loaded.report, loaded.source)

  return (
    <section aria-labelledby="files-heading">
      <h2 id="files-heading" className="mb-3 text-base font-medium text-ink">
        Arquivos
      </h2>
      {!showSpectrograms ? (
        <p className="mb-3 text-sm text-muted">
          Este lote rodou sem espectrograma PNG; a conferência visual fica para uma nova análise
          com a API.
        </p>
      ) : null}
      <div className="overflow-x-auto rounded-lg border border-line bg-surface">
        <table className="min-w-full text-left text-sm tabular-nums">
          <thead className="border-b border-line bg-paper text-muted">
            <tr>
              <th className="px-3 py-2 font-medium">Arquivo</th>
              <th className="px-3 py-2 font-medium">Gravação</th>
              <th className="px-3 py-2 font-medium">Duração</th>
              <th className="px-3 py-2 font-medium">Eventos</th>
              <th className="px-3 py-2 font-medium">Máx. sim.</th>
              {showSpectrograms ? <th className="px-3 py-2 font-medium">Espectrograma</th> : null}
            </tr>
          </thead>
          <tbody>
            {loaded.report.files.map((file) => {
              const expanded = open === file.file
              return (
                <tr key={file.file} className="border-b border-line last:border-0 align-top">
                  <td className="px-3 py-2 font-medium text-ink">{file.file}</td>
                  <td className="px-3 py-2 text-muted">{formatClock(file.recorded_at)}</td>
                  <td className="px-3 py-2">{formatDuration(file.duration_s)}</td>
                  <td className="px-3 py-2">{formatInteger(file.n_events)}</td>
                  <td className="px-3 py-2">{formatInteger(file.max_simultaneous)}</td>
                  {showSpectrograms ? (
                    <td className="px-3 py-2">
                      {file.spectrogram ? (
                        <>
                          <button
                            type="button"
                            className="text-accent underline-offset-2 hover:underline"
                            aria-expanded={expanded}
                            onClick={() => setOpen(expanded ? null : file.file)}
                          >
                            {expanded ? 'Ocultar' : 'Ver PNG'}
                          </button>
                          {expanded ? (
                            <SpectrogramImage
                              src={loaded.spectrogramUrl(file.spectrogram)}
                              alt={`Espectrograma de ${file.file}`}
                            />
                          ) : null}
                        </>
                      ) : (
                        <span className="text-muted">—</span>
                      )}
                    </td>
                  ) : null}
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </section>
  )
}

function SpectrogramImage({ src, alt }: { src: string; alt: string }) {
  const [failed, setFailed] = useState(false)
  if (failed) {
    return <p className="mt-2 max-w-md text-sm text-muted">Espectrograma indisponível.</p>
  }
  return (
    <img
      src={src}
      alt={alt}
      className="mt-2 max-h-80 w-full max-w-xl rounded border border-line bg-paper object-contain"
      onError={() => setFailed(true)}
    />
  )
}
