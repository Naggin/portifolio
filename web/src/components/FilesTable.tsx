import { useState } from 'react'
import { formatClock, formatDuration, formatInteger } from '@/lib/format'
import { reportHasSpectrograms, type LoadedReport } from '@/lib/report'

export function FilesTable({ loaded }: { loaded: LoadedReport }) {
  const [open, setOpen] = useState<string | null>(null)
  const showSpectrograms = reportHasSpectrograms(loaded.report, loaded.source)
  const isCampoBatch = loaded.source === 'campo' || loaded.report.has_spectrograms === false

  return (
    <section aria-labelledby="files-heading">
      <h2 id="files-heading" className="mb-3 text-base font-medium text-ink">
        Arquivos
      </h2>
      {isCampoBatch ? (
        <p className="mb-3 rounded border border-line bg-surface px-3 py-2 text-sm text-muted">
          <strong className="font-medium text-ink">Espectrograma indisponível</strong> neste lote: o
          processamento de campo usou <code className="text-xs">--no-spectrogram</code> (149 962 PNG
          seriam inviáveis). Para conferência visual, use a{' '}
          <a href="/espectrogramas/" className="text-accent hover:underline">
            galeria de validação (madrugada 30:45)
          </a>{' '}
          ou clique <strong className="font-medium text-ink">Ver espectrograma</strong> na tabela
          Eventos (gera PNG sob pedido quando a API está no ar).
        </p>
      ) : !showSpectrograms ? (
        <p className="mb-3 text-sm text-muted">
          Este lote rodou sem espectrograma PNG por arquivo; a conferência visual fica para uma nova
          análise com a API.
        </p>
      ) : null}
      {loaded.report.files.length === 0 ? (
        <p className="rounded-lg border border-line bg-surface px-4 py-6 text-center text-sm text-muted">
          Nenhum arquivo no relatório.
        </p>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-line bg-surface">
          <table className="min-w-full text-left text-sm tabular-nums">
            <thead className="border-b border-line bg-paper text-muted">
              <tr>
                <th className="px-3 py-2 font-medium" title="Nome da gravação">
                  Arquivo
                </th>
                <th
                  className="px-3 py-2 font-medium"
                  title="Início da gravação (nome RYYYYMMDD-HHMMSS; vazio nos MP3s sem data)"
                >
                  Gravação
                </th>
                <th className="px-3 py-2 font-medium" title="Duração total do arquivo">
                  Duração
                </th>
                <th
                  className="px-3 py-2 font-medium"
                  title="Eventos acústicos na banda — soma no arquivo, não machos"
                >
                  Eventos
                </th>
                <th
                  className="px-3 py-2 font-medium"
                  title="Máximo de picos simultâneos estimados (teto estrutural ~2)"
                >
                  Máx. sim.
                </th>
                {showSpectrograms ? (
                  <th
                    className="px-3 py-2 font-medium"
                    title="PNG gerado no processamento (janela de 60 s mais densa em arquivos longos)"
                  >
                    Espectrograma
                  </th>
                ) : null}
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
      )}
    </section>
  )
}

function SpectrogramImage({ src, alt }: { src: string; alt: string }) {
  const [failed, setFailed] = useState(false)
  if (failed) {
    return (
      <p className="mt-2 max-w-md text-sm text-muted">
        Espectrograma indisponível (PNG ausente no servidor).
      </p>
    )
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
