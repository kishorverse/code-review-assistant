import { SeverityCounts } from '@/features/scan/SeverityCounts'
import { ModelLanes } from '@/features/scan/ModelLanes'
import { PipelineRail } from '@/features/scan/PipelineRail'
import { ToolList } from '@/features/scan/ToolList'
import type { Finding } from '@/lib/api'
import type { ScanStage, ToolEvent } from '@/lib/events'
import type { CallRecord } from '@/lib/api'
import type { ReviewPlan } from '@/store/scan-store'

/** The scan as it happens: stages, analyzers, model lanes and what has been found. */
export function ScanProgress({
  stage,
  finishedStages,
  tools,
  calls,
  plan,
  findings,
}: {
  stage: ScanStage | null
  finishedStages: ScanStage[]
  tools: ToolEvent[]
  calls: CallRecord[]
  plan: ReviewPlan | null
  findings: Finding[]
}) {
  return (
    <div className="grid gap-4 lg:grid-cols-3">
      <section className="panel space-y-3 p-4">
        <h2 className="text-[18px]">Pipeline</h2>
        <PipelineRail stage={stage} finishedStages={finishedStages} />
        <ToolList tools={tools} />
      </section>

      <section className="panel space-y-3 p-4">
        <h2 className="text-[18px]">Models</h2>
        {plan && (
          <p className="text-muted text-[13px]">
            {plan.review} chunks to review, {plan.style} for style
            {plan.skipped > 0 && `, ${plan.skipped} skipped`}
          </p>
        )}
        <ModelLanes calls={calls} />
      </section>

      <section className="panel space-y-3 p-4">
        <h2 className="text-[18px]">Found so far</h2>
        <SeverityCounts findings={findings} />
        <ul className="space-y-1 text-[13px]">
          {findings.slice(0, 8).map((finding) => (
            <li key={finding.id} className="mark-in">
              <span className="path text-muted">
                {finding.file_path}:{finding.start_line}
              </span>{' '}
              {finding.title}
            </li>
          ))}
        </ul>
      </section>
    </div>
  )
}
