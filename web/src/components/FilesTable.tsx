import { useState } from 'react'
import { formatClock, formatDuration, formatInteger } from '@/lib/format'
import { fileSpectrogramName, reportHasSpectrograms, type LoadedReport } from '@/lib/report'

export function FilesTable({ loaded }: { loaded: LoadedReport }) {
  const [open, setOpen] = useState<string | null>(null)
  const showSpectrograms = reportHasSpectrograms(loaded.report, loaded.source)
  const isCampoBatch = loaded.source === 'campo' || loaded.report.has_spectrograms === false
  const onDemandSpectrograms = loaded.source === 'live' && isCampoBatch

  return (
    <section aria-labelledby="files-heading">
      <h2 id="files-heading" className="mb-3 text-base font-medium text-ink">
        Arquivos
      </h2>
      {onDemandSpectrograms ? (
        <p className="mb-3 rounded border border-line bg-surface px-3 py-2 text-sm text-muted">
          Este lote de campo rodou com <code className="text-xs">--no-spectrogram</code>.{' '}
          <strong className="font-medium text-ink">Ver PNG</strong> gera a janela de 60 s mais densa
          sob pedido (requer o WAV em <code className="text-xs">data/field/</code>). Para validação
          fixa, use a{' '}
          <a href="/espectrogramas/" className="text-accent hover:underline">
            galeria de validação (madrugada 30:45)
          </a>{' '}
          ou <strong className="font-medium text-ink">Ver espectrograma</strong> na tabela Eventos.
        </p>
      ) : isCampoBatch ? (
        <p className="mb-3 rounded border border-line bg-surface px-3 py-2 text-sm text-muted">
          <strong className="font-medium text-ink">Espectrograma indisponível</strong> neste lote: o
          processamento de campo usou <code className="text-xs">--no-spectrogram</code>. Para
          conferência visual, use a{' '}
          <a href="/espectrogramas/" className="text-accent hover:underline">
            galeria de validação (madrugada 30:45)
          </a>{' '}
          ou carregue o relatório com a API local e o áudio em{' '}
          <code className="text-xs">data/field/</code>.
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
                    title={
                      onDemandSpectrograms
                        ? 'PNG gerado sob pedido (janela de 60 s mais densa em arquivos longos)'
                        : 'PNG gerado no processamento (janela de 60 s mais densa em arquivos longos)'
                    }
                  >
                    Espectrograma
                  </th>
                ) : null}
              </tr>
            </thead>
            <tbody>
              {loaded.report.files.map((file) => {
                const expanded = open === file.file
                const spectrogram = fileSpectrogramName(file)
                return (
                  <tr key={file.file} className="border-b border-line last:border-0 align-top">
                    <td className="px-3 py-2 font-medium text-ink">{file.file}</td>
                    <td className="px-3 py-2 text-muted">{formatClock(file.recorded_at)}</td>
                    <td className="px-3 py-2">{formatDuration(file.duration_s)}</td>
                    <td className="px-3 py-2">{formatInteger(file.n_events)}</td>
                    <td className="px-3 py-2">{formatInteger(file.max_simultaneous)}</td>
                    {showSpectrograms ? (
                      <td className="px-3 py-2">
                        {spectrogram ? (
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
                                src={loaded.spectrogramUrl(spectrogram)}
                                alt={`Espectrograma de ${file.file}`}
                                onDemand={onDemandSpectrograms}
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

function SpectrogramImage({
  src,
  alt,
  onDemand = false,
}: {
  src: string
  alt: string
  onDemand?: boolean
}) {
  const [failed, setFailed] = useState(false)
  const [loading, setLoading] = useState(onDemand)
  if (failed) {
    return (
      <p className="mt-2 max-w-md text-sm text-muted">
        Espectrograma indisponível — confirme que o áudio está em{' '}
        <code className="text-xs">data/field/</code> e que a API está no ar.
      </p>
    )
  }
  return (
    <>
      {loading ? (
        <p className="mt-2 text-sm text-muted" aria-live="polite">
          A gerar o espectrograma (pode demorar em gravações longas)…
        </p>
      ) : null}
      <img
        src={src}
        alt={alt}
        className="mt-2 max-h-80 w-full max-w-xl rounded border border-line bg-paper object-contain"
        onLoad={() => setLoading(false)}
        onError={() => {
          setLoading(false)
          setFailed(true)
        }}
      />
    </>
  )
}
