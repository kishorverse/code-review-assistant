import { STAGES, STAGE_LABEL, type ScanStage } from '@/lib/events'

/** The pipeline, one row per stage, filling in order. */
export function PipelineRail({
  stage,
  finishedStages,
}: {
  stage: ScanStage | null
  finishedStages: ScanStage[]
}) {
  const done = new Set(finishedStages)
  return (
    <ol className="space-y-1.5">
      {STAGES.map((entry) => {
        const isDone = done.has(entry) || stage === 'done'
        const isActive = stage === entry
        return (
          <li key={entry} className="flex items-center gap-2 text-[13px]">
            <span
              aria-hidden
              className={`size-2 rounded-full ${
                isDone ? 'bg-brand' : isActive ? 'bg-brand animate-pulse' : 'bg-line'
              }`}
            />
            <span className={isActive ? 'font-medium' : isDone ? '' : 'text-muted'}>
              {STAGE_LABEL[entry]}
            </span>
            <span className="sr-only">
              {isDone ? 'finished' : isActive ? 'in progress' : 'waiting'}
            </span>
          </li>
        )
      })}
    </ol>
  )
}
