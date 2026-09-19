import { describe, expect, it } from 'vitest'

import { describeEvent } from '@/lib/activity'
import { makeCall, makeFinding } from '@/test/fixtures'

describe('activity log', () => {
  it('reports a finished analyzer with its count and time', () => {
    const line = describeEvent(
      {
        kind: 'tool',
        tool: 'bandit',
        state: 'ok',
        finding_count: 1,
        duration_ms: 1500,
        message: null,
      },
      0,
    )
    expect(line).toEqual({ at: 0, source: 'bandit', text: '1 finding in 1.5 s', tone: 'ok' })
  })

  it('warns when a provider passes a call on', () => {
    const line = describeEvent(
      { kind: 'llm_call', call: makeCall({ status: 'rate_limited', provider: 'gemini' }) },
      0,
    )
    expect(line?.source).toBe('gemini')
    expect(line?.text).toBe('review app/db.py rate limited, trying the next provider')
    expect(line?.tone).toBe('warn')
  })

  it('leaves out events that would only add noise', () => {
    expect(describeEvent({ kind: 'finding', finding: makeFinding() }, 0)).toBeNull()
    expect(describeEvent({ kind: 'llm_call', call: makeCall({ status: 'skipped' }) }, 0)).toBeNull()
    expect(
      describeEvent(
        {
          kind: 'tool',
          tool: 'ruff',
          state: 'started',
          finding_count: 0,
          duration_ms: 0,
          message: null,
        },
        0,
      ),
    ).toBeNull()
  })

  it('shows why a scan failed', () => {
    const line = describeEvent({ kind: 'status', status: 'failed', message: 'Archive is empty' }, 0)
    expect(line).toMatchObject({ text: 'Archive is empty', tone: 'error' })
  })
})
