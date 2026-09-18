import { describe, expect, it } from 'vitest'

import { dedent } from '@/lib/text'

describe('dedent', () => {
  it('removes shared indentation and keeps relative indentation', () => {
    expect(dedent('    if ready:\n        go()')).toBe('if ready:\n    go()')
  })

  it('ignores blank lines and leaves unindented text alone', () => {
    expect(dedent('  a\n\n  b')).toBe('a\n\nb')
    expect(dedent('x = 1')).toBe('x = 1')
    expect(dedent('')).toBe('')
  })
})
