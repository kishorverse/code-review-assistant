import { describe, expect, it } from 'vitest'

import { forgetScan, rememberScan, timeAgo } from '@/lib/recent'

describe('recent reviews', () => {
  it('keeps the latest review first, without duplicates, and forgets deleted ones', () => {
    rememberScan({ id: 'a', source: 'a.zip', createdAt: '2026-09-18T10:00:00Z' })
    rememberScan({ id: 'b', source: 'b.zip', createdAt: '2026-09-18T11:00:00Z' })
    rememberScan({ id: 'a', source: 'a.zip', createdAt: '2026-09-18T10:00:00Z' })

    const stored = () =>
      (JSON.parse(localStorage.getItem('margin-recent-scans') ?? '[]') as { id: string }[]).map(
        (scan) => scan.id,
      )
    expect(stored()).toEqual(['a', 'b'])

    forgetScan('b')
    expect(stored()).toEqual(['a'])
  })

  it('describes times briefly', () => {
    const now = new Date('2026-09-18T12:00:00Z')
    expect(timeAgo('2026-09-18T11:59:30Z', now)).toBe('just now')
    expect(timeAgo('2026-09-18T11:45:00Z', now)).toBe('15 min ago')
    expect(timeAgo('2026-09-18T09:00:00Z', now)).toBe('3 h ago')
  })
})
