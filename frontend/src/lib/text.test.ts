import { describe, expect, it } from 'vitest'

import { commonFolder, dedent } from '@/lib/text'

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

describe('commonFolder', () => {
  it('finds the folder all paths share', () => {
    expect(commonFolder(['shop/a.py', 'shop/b.py'])).toBe('shop/')
    expect(commonFolder(['src/app/a.py', 'src/app/x/b.py', 'src/c.py'])).toBe('src/')
  })

  it('is empty when the paths share no folder', () => {
    expect(commonFolder(['a.py', 'shop/b.py'])).toBe('')
    expect(commonFolder(['shop/a.py', 'shopping/b.py'])).toBe('')
    expect(commonFolder([])).toBe('')
  })
})
