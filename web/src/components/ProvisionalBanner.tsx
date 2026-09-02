import type { DetectionReport } from '@/lib/types'

const STRUCTURAL_CEILING = 2

export function ProvisionalBanner({ report }: { report: DetectionReport }) {
  const showCeiling =
    report.summary.max_simultaneous <= STRUCTURAL_CEILING &&
    report.files.every((file) => file.max_simultaneous <= STRUCTURAL_CEILING)

  return (
    <div className="flex flex-col gap-3">
      <p
        className="rounded border border-warn/40 bg-warn-soft px-4 py-3 text-sm text-warn"
        role="note"
      >
        <strong className="font-medium">PROVISÓRIO</strong> — estes números contam{' '}
        <strong className="font-medium">eventos acústicos</strong> na banda calibrada{' '}
        {report.config.lowcut_hz / 1000}–{report.config.highcut_hz / 1000} kHz. Não são machos no
        açude, indivíduos identificados nem prova de espécie em cada linha.
      </p>
      {showCeiling ? (
        <p
          className="rounded border border-accent/30 bg-accent-soft px-4 py-3 text-sm text-ink"
          role="note"
        >
          <strong className="font-medium text-accent">Máx. simultâneos = 1–2 em todo o lote</strong>{' '}
          — isto é o <em>teto estrutural</em> da banda de 600 Hz com separação de 400 Hz entre
          picos, não uma contagem de animais. Dois machos no mesmo tom podem aparecer como um só.
        </p>
      ) : null}
    </div>
  )
}
