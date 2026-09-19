import { Check, LoaderCircle } from 'lucide-react'

import { STAGES, STAGE_LABEL, type ScanStage } from '@/lib/events'

/** Short names, so all six steps fit on one line; the log uses the full ones. */
const STEP: Record<ScanStage, string> = {
  ingesting: 'Unpack',
  preprocessing: 'Parse',
  analyzing: 'Analyzers',
  reviewing: 'AI review',
  verifying: 'Cross-check',
  summarizing: 'Summary',
  done: 'Done',
}

/** The pipeline as a stepper: finished stages ticked, the current one spinning. */
export function PipelineRail({
  stage,
  finishedStages,
}: {
  stage: ScanStage | null
  finishedStages: ScanStage[]
}) {
  const done = new Set(finishedStages)
  const finished = STAGES.filter((entry) => done.has(entry) || stage === 'done').length
  // Half a step of credit for the one in progress, so the bar never sits still.
  const inProgress = stage && stage !== 'done' && !done.has(stage) ? 0.5 : 0
  const progress = Math.min(100, ((finished + inProgress) / STAGES.length) * 100)
  const current = stage && stage !== 'done' ? STAGE_LABEL[stage] : null

  return (
    <section className="rise panel overflow-hidden" aria-label="Pipeline">
      <div className="flex items-center gap-3 px-5 pt-4">
        <p className="eyebrow">Pipeline</p>
        <p key={current ?? 'idle'} className="fade-in text-muted min-w-0 truncate text-[12.5px]">
          {current ? `${current}…` : stage === 'done' ? 'All stages finished' : 'Starting…'}
        </p>
        <span className="text-text ml-auto text-[12.5px] font-medium tabular-nums">
          {Math.round(progress)}%
        </span>
      </div>
      <div className="bg-subtle mx-5 mt-3 h-1 overflow-hidden rounded-full" aria-hidden>
        <div
          className="relative h-full rounded-full bg-[linear-gradient(90deg,var(--color-accent),var(--color-accent-2))] transition-[width] duration-1000 ease-out-expo"
          style={{ width: `${progress}%` }}
        >
          {stage !== 'done' && (
            <span className="animate-shimmer absolute inset-0 bg-[linear-gradient(90deg,transparent,rgb(255_255_255/0.5),transparent)] bg-[length:200%_100%]" />
          )}
        </div>
      </div>
      <ol className="grid grid-cols-2 gap-y-4 px-5 pt-4 pb-4.5 sm:grid-cols-3 lg:grid-cols-6">
        {STAGES.map((entry, index) => {
          const isDone = done.has(entry) || stage === 'done'
          const isActive = stage === entry && !isDone
          return (
            <li key={entry} className="flex min-w-0 items-center gap-2.5">
              <span
                className={`relative grid size-7 shrink-0 place-items-center rounded-full border text-[11px] font-medium transition-all duration-500 ease-spring ${
                  isDone
                    ? 'border-transparent bg-[linear-gradient(135deg,var(--color-accent),var(--color-accent-2))] text-on-accent scale-100'
                    : isActive
                      ? 'border-accent text-accent-text bg-accent-soft animate-pulse-ring scale-105'
                      : 'border-line text-faint bg-surface'
                }`}
              >
                {isDone ? (
                  <Check
                    aria-hidden
                    className="size-3.5 [animation:rise_400ms_var(--ease-spring)_both]"
                    strokeWidth={2.75}
                  />
                ) : isActive ? (
                  <LoaderCircle aria-hidden className="size-3.5 animate-spin" />
                ) : (
                  <span className="mono">{index + 1}</span>
                )}
              </span>
              <span
                title={STAGE_LABEL[entry]}
                className={`shrink-0 text-[12.5px] transition-colors duration-300 ${
                  isActive ? 'text-text font-medium' : isDone ? 'text-text' : 'text-faint'
                }`}
              >
                {STEP[entry]}
              </span>
              <span className="sr-only">
                {isDone ? 'finished' : isActive ? 'in progress' : 'waiting'}
              </span>
              {index < STAGES.length - 1 && (
                <span
                  aria-hidden
                  className="bg-line relative mr-3 hidden h-px min-w-3 flex-1 overflow-hidden lg:block"
                >
                  <span
                    className={`bg-accent/60 absolute inset-0 origin-left transition-transform duration-700 ease-out-expo ${
                      isDone ? 'scale-x-100' : 'scale-x-0'
                    }`}
                  />
                </span>
              )}
            </li>
          )
        })}
      </ol>
    </section>
  )
}
