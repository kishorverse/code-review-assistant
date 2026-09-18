import type { ReviewSummary } from '@/lib/api'

/** The models' executive summary. It is written from finding titles, not code. */
export function SummaryCard({ summary }: { summary: ReviewSummary }) {
  return (
    <section className="panel space-y-2 p-4">
      <h2 className="text-[18px]">Summary</h2>
      <p className="font-medium">{summary.headline}</p>
      {summary.top_risks.length > 0 && (
        <div>
          <h3 className="text-muted text-[13px] font-medium">Top risks</h3>
          <ul className="list-disc space-y-0.5 pl-4 text-[13px]">
            {summary.top_risks.map((risk, index) => (
              <li key={index}>
                <strong>{risk.title}</strong>
                {risk.files.length > 0 && (
                  <span className="path text-muted"> {risk.files.join(', ')}</span>
                )}
                {risk.why && <span> — {risk.why}</span>}
              </li>
            ))}
          </ul>
        </div>
      )}
      {summary.recommended_next_steps.length > 0 && (
        <div>
          <h3 className="text-muted text-[13px] font-medium">Next steps</h3>
          <ol className="list-decimal space-y-0.5 pl-4 text-[13px]">
            {summary.recommended_next_steps.map((step, index) => (
              <li key={index}>{step}</li>
            ))}
          </ol>
        </div>
      )}
    </section>
  )
}
