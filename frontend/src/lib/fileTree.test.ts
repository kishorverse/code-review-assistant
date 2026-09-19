import { describe, expect, it } from 'vitest'

import type { FileEntry } from '@/lib/api'
import { ancestors, buildFileTree } from '@/lib/fileTree'

const file = (path: string, findings = 0, highest: FileEntry['highest_severity'] = null) => ({
  path,
  language: 'python',
  lines: 10,
  findings,
  highest_severity: highest,
})

describe('buildFileTree', () => {
  it('nests files in folders, folders first, and totals each folder', () => {
    const tree = buildFileTree([
      file('app/server.py', 3, 'medium'),
      file('README.md'),
      file('app/db/models.py', 2, 'high'),
    ])

    expect(tree.children.map((child) => child.name)).toEqual(['app', 'README.md'])
    const app = tree.children[0]
    expect(app?.kind).toBe('folder')
    if (app?.kind !== 'folder') return
    expect(app.findings).toBe(5)
    expect(app.highest).toBe('high')
    expect(app.children.map((child) => child.name)).toEqual(['db', 'server.py'])
  })

  it('lists the folders above a file', () => {
    expect(ancestors('a/b/c.py')).toEqual(['a', 'a/b'])
    expect(ancestors('c.py')).toEqual([])
  })
})
