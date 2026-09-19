import { SeverityCounts } from '@/features/scan/SeverityCounts'
import type { Finding, ScanDetail } from '@/lib/api'
import { stagger } from '@/lib/utils'

/** How many findings the report holds, by severity, and how much of the code was read. */
export function FindingsOverview({
  reported,
  summary,
}: {
  reported: Finding[]
  summary: ScanDetail['summary']
}) {
  return (
    <section className="rise panel flex flex-col px-5 py-4.5" style={stagger(1)}>
      <h2 className="eyebrow">Findings</h2>
      <p className="mt-3 flex items-baseline gap-2">
        <span className="display text-[56px] leading-none tabular-nums">{reported.length}</span>
        <span className="text-faint text-[13px]">in the report</span>
      </p>
      <div className="mt-4">
        <SeverityCounts findings={reported} />
      </div>
      {summary && (
        <p className="text-muted border-line/70 mt-auto flex gap-4 border-t pt-3 text-[12.5px]">
          <span>
            <span className="text-text font-medium tabular-nums">{summary.files_scanned}</span>{' '}
            files scanned
          </span>
          <span>
            <span className="text-text font-medium tabular-nums">{summary.files_reviewed}</span>{' '}
            read by a model
          </span>
        </p>
      )}
    </section>
  )
}
