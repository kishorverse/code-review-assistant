import { Panel } from '@/components/Panel'
import { SeverityChip } from '@/components/SeverityChip'
import { ActivityLog } from '@/features/scan/ActivityLog'
import { ModelLanes } from '@/features/scan/ModelLanes'
import { PipelineRail } from '@/features/scan/PipelineRail'
import { SeverityCounts } from '@/features/scan/SeverityCounts'
import { ToolList } from '@/features/scan/ToolList'
import type { ActivityLine } from '@/lib/activity'
import type { CallRecord, Finding } from '@/lib/api'
import type { ScanStage, ToolEvent } from '@/lib/events'
import type { ReviewPlan } from '@/store/scan-store'

/** The scan as it happens: stages, analyzers, models, the log and what has been found. */
export function ScanProgress({
  stage,
  finishedStages,
  tools,
  calls,
  plan,
  findings,
  activity,
}: {
  stage: ScanStage | null
  finishedStages: ScanStage[]
  tools: ToolEvent[]
  calls: CallRecord[]
  plan: ReviewPlan | null
  findings: Finding[]
  activity: ActivityLine[]
}) {
  return (
    <div className="space-y-4">
      <PipelineRail stage={stage} finishedStages={finishedStages} />
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_400px]">
        <div className="min-w-0 space-y-4">
          <div className="grid gap-4 lg:grid-cols-2">
            <Panel title="Analyzers" order={1}>
              <ToolList tools={tools} />
            </Panel>
            <Panel
              title="Models"
              order={2}
              aside={
                plan &&
                `${plan.review} to review · ${plan.style} for style${plan.skipped ? ` · ${plan.skipped} skipped` : ''}`
              }
            >
              <ModelLanes calls={calls} />
            </Panel>
          </div>
          <Panel title="Activity" order={3}>
            <ActivityLog lines={activity} />
          </Panel>
        </div>
        <Panel
          title="Found so far"
          aside={`${findings.length}`}
          order={2}
          className="xl:self-start"
        >
          <div className="space-y-4 px-4 py-3.5">
            <SeverityCounts findings={findings} />
            {findings.length === 0 ? (
              <div className="flex flex-col items-center gap-2 py-8 text-center">
                <span className="relative flex size-2.5" aria-hidden>
                  <span className="bg-accent absolute inset-0 animate-ping rounded-full opacity-50" />
                  <span className="bg-accent relative size-2.5 rounded-full" />
                </span>
                <p className="text-muted text-[13px]">Nothing yet. Findings stream in here.</p>
              </div>
            ) : (
              <ul className="divide-line -mx-4 divide-y border-y border-line">
                {findings.slice(0, 12).map((finding) => (
                  <li
                    key={finding.id}
                    className="rise hover:bg-subtle/60 space-y-1 px-4 py-2.5 transition-colors"
                  >
                    <div className="flex items-start gap-2">
                      <SeverityChip severity={finding.severity} />
                      <span className="min-w-0 flex-1 text-[13px] leading-snug">
                        {finding.title}
                      </span>
                    </div>
                    <p className="mono text-faint truncate text-[11.5px]">
                      {finding.file_path}:{finding.start_line} · {finding.sources.join(', ')}
                    </p>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </Panel>
      </div>
    </div>
  )
}
