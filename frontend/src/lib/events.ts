/** The scan event stream.
 *
 * Server-sent events are not part of the OpenAPI document, so these shapes
 * mirror the stream described in `docs/api.md`. Each event's name equals its
 * `kind`, and every payload is one of the types below.
 */
import type { CallRecord, Finding, ScanStatus } from '@/lib/api'

export type ScanStage =
  'ingesting' | 'preprocessing' | 'analyzing' | 'reviewing' | 'verifying' | 'summarizing' | 'done'

export type ToolState = 'started' | 'ok' | 'failed' | 'skipped' | 'timed_out'

export interface StageEvent {
  kind: 'stage'
  stage: ScanStage
}

export interface ToolEvent {
  kind: 'tool'
  tool: string
  state: ToolState
  finding_count: number
  duration_ms: number
  message: string | null
}

export interface FindingEvent {
  kind: 'finding'
  finding: Finding
}

export interface ReviewPlanEvent {
  kind: 'review_plan'
  review_chunks: number
  style_chunks: number
  skipped_chunks: number
}

export interface CallEvent {
  kind: 'llm_call'
  call: CallRecord
}

export interface StatusEvent {
  kind: 'status'
  status: ScanStatus
  message: string | null
}

export type ScanEvent =
  StageEvent | ToolEvent | FindingEvent | ReviewPlanEvent | CallEvent | StatusEvent

export const EVENT_KINDS: ScanEvent['kind'][] = [
  'stage',
  'tool',
  'finding',
  'review_plan',
  'llm_call',
  'status',
]

export const STAGES: ScanStage[] = [
  'ingesting',
  'preprocessing',
  'analyzing',
  'reviewing',
  'verifying',
  'summarizing',
]

export const STAGE_LABEL: Record<ScanStage, string> = {
  ingesting: 'Unpacking',
  preprocessing: 'Parsing and chunking',
  analyzing: 'Running analyzers',
  reviewing: 'AI review',
  verifying: 'Cross-checking',
  summarizing: 'Summarizing',
  done: 'Done',
}
