import { beforeEach, describe, expect, it } from 'vitest'

import { groupCalls, selectIsFinished, useScanStore } from '@/store/scan-store'
import { makeCall, makeFinding } from '@/test/fixtures'

describe('scan store', () => {
  beforeEach(() => useScanStore.getState().start('scan1'))

  it('tracks stages, tools and the review plan', () => {
    const { apply } = useScanStore.getState()

    apply({ kind: 'stage', stage: 'ingesting' })
    apply({ kind: 'stage', stage: 'analyzing' })
    apply({
      kind: 'tool',
      tool: 'ruff',
      state: 'started',
      finding_count: 0,
      duration_ms: 0,
      message: null,
    })
    apply({
      kind: 'tool',
      tool: 'ruff',
      state: 'ok',
      finding_count: 3,
      duration_ms: 120,
      message: null,
    })
    apply({ kind: 'review_plan', review_chunks: 4, style_chunks: 2, skipped_chunks: 1 })

    const state = useScanStore.getState()
    expect(state.stage).toBe('analyzing')
    expect(state.finishedStages).toEqual(['ingesting'])
    expect(state.tools).toHaveLength(1)
    expect(state.tools[0]?.finding_count).toBe(3)
    expect(state.plan).toEqual({ review: 4, style: 2, skipped: 1 })
    expect(state.activity.map((line) => `${line.source}: ${line.text}`)).toEqual([
      'scan: Unpacking',
      'scan: Running analyzers',
      'ruff: 3 findings in 120 ms',
      'plan: 4 chunks for review, 2 for style, 1 skipped',
    ])
  })

  it('replaces a finding when a later event carries the same id', () => {
    const { apply } = useScanStore.getState()

    apply({ kind: 'finding', finding: makeFinding() })
    apply({ kind: 'finding', finding: makeFinding({ sources: ['bandit', 'nvidia'] }) })

    const findings = Object.values(useScanStore.getState().findings)
    expect(findings).toHaveLength(1)
    expect(findings[0]?.sources).toEqual(['bandit', 'nvidia'])
  })

  it('records calls and the final status', () => {
    const { apply } = useScanStore.getState()

    apply({ kind: 'llm_call', call: makeCall() })
    apply({ kind: 'llm_call', call: makeCall({ provider: 'gemini', status: 'unavailable' }) })
    apply({ kind: 'status', status: 'done', message: null })

    const state = useScanStore.getState()
    expect(selectIsFinished(state)).toBe(true)
    expect([...groupCalls(state.calls).keys()]).toEqual(['nvidia', 'gemini'])
  })

  it('starts clean for each scan', () => {
    useScanStore.getState().apply({ kind: 'finding', finding: makeFinding() })

    useScanStore.getState().start('scan2')

    const state = useScanStore.getState()
    expect(Object.keys(state.findings)).toEqual([])
    expect(state.scanId).toBe('scan2')
  })
})
