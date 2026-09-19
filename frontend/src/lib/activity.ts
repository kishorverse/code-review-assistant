/** The scan's events as a readable log, like a terminal beside the dashboard. */
import type { ScanEvent } from '@/lib/events'
import { STAGE_LABEL } from '@/lib/events'

export type Tone = 'info' | 'ok' | 'warn' | 'error'

export interface ActivityLine {
  at: number
  source: string
  text: string
  tone: Tone
}

const CALL_STATUS: Record<string, string> = {
  ok: 'answered',
  cached: 'answered from cache',
  rate_limited: 'rate limited, trying the next provider',
  quota_exhausted: 'quota used up, trying the next provider',
  auth_failed: 'key rejected',
  misconfigured: 'misconfigured',
  unavailable: 'unavailable, trying the next provider',
  rejected: 'answer unusable, trying the next provider',
  skipped: 'skipped (paused or over its limit)',
}

function seconds(ms: number): string {
  return ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`
}

/** The log line for an event, or ``null`` for events the log leaves out. */
export function describeEvent(event: ScanEvent, at: number): ActivityLine | null {
  switch (event.kind) {
    case 'stage':
      return event.stage === 'done'
        ? null
        : { at, source: 'scan', text: STAGE_LABEL[event.stage], tone: 'info' }
    case 'tool':
      if (event.state === 'started') return null
      return {
        at,
        source: event.tool,
        text:
          event.state === 'ok'
            ? `${event.finding_count} finding${event.finding_count === 1 ? '' : 's'} in ${seconds(event.duration_ms)}`
            : `${event.state.replace('_', ' ')}${event.message ? `: ${event.message}` : ''}`,
        tone: event.state === 'ok' ? 'ok' : 'warn',
      }
    case 'review_plan':
      return {
        at,
        source: 'plan',
        text: `${event.review_chunks} chunks for review, ${event.style_chunks} for style${
          event.skipped_chunks ? `, ${event.skipped_chunks} skipped` : ''
        }`,
        tone: 'info',
      }
    case 'llm_call': {
      const { call } = event
      if (call.status === 'skipped') return null
      const ok = call.status === 'ok' || call.status === 'cached'
      return {
        at,
        source: call.provider,
        text: `${call.task} ${call.file_path ?? ''} ${CALL_STATUS[call.status] ?? call.status}${
          ok && call.latency_ms ? ` in ${seconds(call.latency_ms)}` : ''
        }`.replace(/\s+/g, ' '),
        tone: ok ? 'ok' : 'warn',
      }
    }
    case 'status':
      if (event.status === 'done')
        return { at, source: 'scan', text: 'Review finished', tone: 'ok' }
      if (event.status === 'failed')
        return { at, source: 'scan', text: event.message ?? 'The scan failed', tone: 'error' }
      return null
    case 'finding':
      return null
  }
}
