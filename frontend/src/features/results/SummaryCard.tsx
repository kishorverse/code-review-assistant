import { Sparkles, TriangleAlert } from 'lucide-react'

import type { ReviewSummary } from '@/lib/api'
import { stagger } from '@/lib/utils'

/** The models' executive summary. It is written from finding titles, not code. */
export function SummaryCard({ summary }: { summary: ReviewSummary }) {
  return (
    <section className="rise panel ring-gradient h-full px-5 py-4.5" style={stagger(2)}>
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 overflow-hidden rounded-[inherit]"
      >
        <div className="absolute -top-24 -right-24 size-64 rounded-full bg-[radial-gradient(circle,color-mix(in_srgb,var(--color-accent-2)_14%,transparent),transparent_70%)]" />
      </div>
      <h2 className="eyebrow relative flex items-center gap-1.5">
        <Sparkles aria-hidden className="text-accent-text size-3.5" />
        Summary
      </h2>
      <p className="relative mt-2.5 text-[16px] leading-snug font-medium tracking-tight text-pretty">
        {summary.headline}
      </p>
      <div className="relative mt-4 grid gap-5 lg:grid-cols-2">
        {summary.top_risks.length > 0 && (
          <div>
            <h3 className="text-faint mb-2 text-[12px] font-medium">Top risks</h3>
            <ul className="space-y-2">
              {summary.top_risks.slice(0, 4).map((risk, index) => (
                <li
                  key={index}
                  className="rise flex gap-2 text-[12.5px] leading-snug"
                  style={stagger(index + 4)}
                >
                  <TriangleAlert aria-hidden className="text-high mt-0.5 size-3.5 shrink-0" />
                  <span className="min-w-0">
                    <span className="font-medium">{risk.title}</span>
                    {risk.files.length > 0 && (
                      <span className="mono text-faint block truncate text-[11.5px]">
                        {risk.files.join(', ')}
                      </span>
                    )}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}
        {summary.recommended_next_steps.length > 0 && (
          <div>
            <h3 className="text-faint mb-2 text-[12px] font-medium">Next steps</h3>
            <ol className="space-y-2">
              {summary.recommended_next_steps.slice(0, 4).map((step, index) => (
                <li
                  key={index}
                  className="rise flex gap-2.5 text-[12.5px] leading-snug"
                  style={stagger(index + 5)}
                >
                  <span className="bg-accent-soft text-accent-text mono grid size-4.5 shrink-0 place-items-center rounded-full text-[10px] font-medium">
                    {index + 1}
                  </span>
                  <span className="min-w-0">{step}</span>
                </li>
              ))}
            </ol>
          </div>
        )}
      </div>
    </section>
  )
}
