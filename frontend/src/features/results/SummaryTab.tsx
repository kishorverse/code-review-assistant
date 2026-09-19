import { CircleCheck, ScanSearch } from 'lucide-react'

import { FindingsOverview } from '@/features/results/FindingsOverview'
import { ScoreCard } from '@/features/results/ScoreCard'
import { SummaryCard } from '@/features/results/SummaryCard'
import type { Category, Finding, ScanDetail } from '@/lib/api'
import { stagger } from '@/lib/utils'

const CATEGORY_LABEL: Record<Category, string> = {
  bug: 'Bugs',
  security: 'Security',
  performance: 'Performance',
  maintainability: 'Maintainability',
  style: 'Style',
  typing: 'Typing',
}

/** The whole review on one page: the models' summary, the score, and where findings fall. */
export function SummaryTab({ detail, reported }: { detail: ScanDetail; reported: Finding[] }) {
  const strengths = detail.ai_summary?.strengths ?? []
  return (
    <div className="grid items-start gap-4 pb-2 lg:grid-cols-[minmax(0,1fr)_340px]">
      <div className="min-w-0 space-y-4">
        {detail.ai_summary ? (
          <SummaryCard summary={detail.ai_summary} />
        ) : (
          <section className="rise panel flex flex-col items-center gap-3 px-5 py-10 text-center">
            <span className="border-line bg-subtle text-faint grid size-10 place-items-center rounded-xl border">
              <ScanSearch aria-hidden className="size-4.5" />
            </span>
            <p className="text-muted max-w-sm text-[13px] leading-relaxed">
              No model summary for this review: it ran the static analyzers only.
            </p>
          </section>
        )}
        <div className="grid gap-4 md:grid-cols-2">
          <CategoryBreakdown findings={reported} />
          {strengths.length > 0 && (
            <section className="rise panel px-5 py-4.5" style={stagger(4)}>
              <h2 className="eyebrow">Strengths</h2>
              <ul className="mt-3 space-y-2">
                {strengths.map((strength, index) => (
                  <li key={index} className="flex gap-2 text-[12.5px] leading-snug">
                    <CircleCheck aria-hidden className="text-success mt-0.5 size-3.5 shrink-0" />
                    <span>{strength}</span>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </div>
      </div>
      <div className="space-y-4">
        {detail.score && <ScoreCard score={detail.score} />}
        <FindingsOverview reported={reported} summary={detail.summary} />
      </div>
    </div>
  )
}

function CategoryBreakdown({ findings }: { findings: Finding[] }) {
  const counts = new Map<Category, number>()
  for (const finding of findings)
    counts.set(finding.category, (counts.get(finding.category) ?? 0) + 1)
  const rows = [...counts.entries()].sort((a, b) => b[1] - a[1])
  const most = Math.max(1, ...rows.map(([, count]) => count))
  return (
    <section className="rise panel px-5 py-4.5" style={stagger(3)}>
      <h2 className="eyebrow">By category</h2>
      {rows.length === 0 ? (
        <p className="text-muted mt-3 text-[13px]">No findings in the report.</p>
      ) : (
        <ul className="mt-3 space-y-2.5">
          {rows.map(([category, count], index) => (
            <li
              key={category}
              className="grid grid-cols-[112px_minmax(0,1fr)_28px] items-center gap-3 text-[12.5px]"
            >
              <span className="text-muted">{CATEGORY_LABEL[category] ?? category}</span>
              <span className="bg-subtle h-1.5 overflow-hidden rounded-full" aria-hidden>
                <span
                  className="grow-x block h-full rounded-full bg-[linear-gradient(90deg,var(--color-accent),var(--color-accent-2))]"
                  style={{ width: `${(count / most) * 100}%`, ...stagger(index) }}
                />
              </span>
              <span className="text-right font-medium tabular-nums">{count}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
