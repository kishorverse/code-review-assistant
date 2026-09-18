import { describe, expect, it } from 'vitest'

import { EMPTY_FILTER, applyFilter, isReported } from '@/lib/filters'
import { makeFinding } from '@/test/fixtures'

const STATIC_HIGH = makeFinding({ id: 'a' })
const AI_MEDIUM = makeFinding({
  id: 'b',
  severity: 'medium',
  category: 'bug',
  sources: ['nvidia'],
  confidence: 0.9,
  file_path: 'app/api.py',
})
const AI_UNSURE = makeFinding({
  id: 'c',
  sources: ['hf-small'],
  confidence: 0.4,
  category: 'style',
})
const DISMISSED = makeFinding({ id: 'd', status: 'dismissed_by_ai' })
const CONFIRMED = makeFinding({ id: 'e', sources: ['bandit', 'nvidia'], severity: 'low' })
const ALL = [STATIC_HIGH, AI_MEDIUM, AI_UNSURE, DISMISSED, CONFIRMED]

const ids = (findings: { id: string }[]) => findings.map((finding) => finding.id)

describe('finding filters', () => {
  it('hides dismissed, rejected and unconfident AI findings by default', () => {
    expect(ids(applyFilter(ALL, EMPTY_FILTER, 0.6))).toEqual(['a', 'b', 'e'])
    expect(ids(applyFilter(ALL, { ...EMPTY_FILTER, includeHidden: true }, 0.6))).toEqual(ids(ALL))
  })

  it('never hides analyzer findings for low confidence', () => {
    expect(isReported(makeFinding({ confidence: 0.2 }), 0.6)).toBe(true)
    expect(isReported(makeFinding({ status: 'rejected' }), 0.6)).toBe(false)
  })

  it('filters by minimum severity, category, file and source', () => {
    expect(ids(applyFilter(ALL, { ...EMPTY_FILTER, minSeverity: 'medium' }, 0.6))).toEqual([
      'a',
      'b',
    ])
    expect(ids(applyFilter(ALL, { ...EMPTY_FILTER, category: 'bug' }, 0.6))).toEqual(['b'])
    expect(ids(applyFilter(ALL, { ...EMPTY_FILTER, file: 'app/api.py' }, 0.6))).toEqual(['b'])
    expect(ids(applyFilter(ALL, { ...EMPTY_FILTER, source: 'tools' }, 0.6))).toEqual(['a', 'e'])
    expect(ids(applyFilter(ALL, { ...EMPTY_FILTER, source: 'models' }, 0.6))).toEqual(['b', 'e'])
  })
})
