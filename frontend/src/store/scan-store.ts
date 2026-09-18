/** Live state of one scan, fed by its event stream.
 *
 * Findings are kept by id, because a later event for the same id replaces the
 * earlier version: AI review updates findings that static analysis reported.
 */
import { create } from 'zustand'

import type { CallRecord, Finding, ScanStatus } from '@/lib/api'
import type { ScanEvent, ScanStage, ToolEvent } from '@/lib/events'

export interface ReviewPlan {
  review: number
  style: number
  skipped: number
}

interface ScanState {
  scanId: string | null
  status: ScanStatus | null
  message: string | null
  stage: ScanStage | null
  finishedStages: ScanStage[]
  tools: ToolEvent[]
  calls: CallRecord[]
  plan: ReviewPlan | null
  findings: Record<string, Finding>
  start: (scanId: string) => void
  apply: (event: ScanEvent) => void
}

const EMPTY = {
  status: null,
  message: null,
  stage: null,
  finishedStages: [] as ScanStage[],
  tools: [] as ToolEvent[],
  calls: [] as CallRecord[],
  plan: null,
  findings: {} as Record<string, Finding>,
}

export const useScanStore = create<ScanState>((set) => ({
  scanId: null,
  ...EMPTY,

  /** Begin following a scan, discarding any previous scan's state. */
  start: (scanId) => set({ scanId, ...EMPTY }),

  apply: (event) =>
    set((state) => {
      switch (event.kind) {
        case 'status':
          return { status: event.status, message: event.message }
        case 'stage':
          return {
            stage: event.stage,
            finishedStages: state.stage ? [...state.finishedStages, state.stage] : [],
          }
        case 'tool':
          return { tools: upsertTool(state.tools, event) }
        case 'review_plan':
          return {
            plan: {
              review: event.review_chunks,
              style: event.style_chunks,
              skipped: event.skipped_chunks,
            },
          }
        case 'llm_call':
          return { calls: [...state.calls, event.call] }
        case 'finding':
          return { findings: { ...state.findings, [event.finding.id]: event.finding } }
      }
    }),
}))

function upsertTool(tools: ToolEvent[], event: ToolEvent): ToolEvent[] {
  const index = tools.findIndex((tool) => tool.tool === event.tool)
  if (index === -1) return [...tools, event]
  const updated = [...tools]
  updated[index] = event
  return updated
}

/** The findings seen so far, in arrival order. */
export const selectFindings = (state: { findings: Record<string, Finding> }): Finding[] =>
  Object.values(state.findings)

export const selectIsFinished = (state: { status: ScanStatus | null }): boolean =>
  state.status === 'done' || state.status === 'failed'

/** Calls per provider, for the model lanes. */
export function groupCalls(calls: CallRecord[]): Map<string, CallRecord[]> {
  const lanes = new Map<string, CallRecord[]>()
  for (const call of calls) {
    lanes.set(call.provider, [...(lanes.get(call.provider) ?? []), call])
  }
  return lanes
}
