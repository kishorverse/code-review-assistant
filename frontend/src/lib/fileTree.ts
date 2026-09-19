/** The scan's files as a folder tree, for the explorer. */
import type { FileEntry, Severity } from '@/lib/api'
import { severityRank } from '@/lib/severity'

export interface FolderNode {
  kind: 'folder'
  name: string
  path: string
  children: TreeNode[]
  findings: number
  highest: Severity | null
}

export interface FileNode {
  kind: 'file'
  name: string
  path: string
  entry: FileEntry
}

export type TreeNode = FolderNode | FileNode

function higher(a: Severity | null, b: Severity | null): Severity | null {
  if (!a) return b
  if (!b) return a
  return severityRank(a) >= severityRank(b) ? a : b
}

/**
 * Build the tree. Folders come before files, each sorted by name, and every folder
 * carries the total and the most severe finding of everything inside it.
 */
export function buildFileTree(files: FileEntry[]): FolderNode {
  const root: FolderNode = {
    kind: 'folder',
    name: '',
    path: '',
    children: [],
    findings: 0,
    highest: null,
  }
  for (const entry of files) {
    const parts = entry.path.split('/')
    let folder = root
    parts.slice(0, -1).forEach((name, index) => {
      const path = parts.slice(0, index + 1).join('/')
      let next = folder.children.find(
        (child): child is FolderNode => child.kind === 'folder' && child.name === name,
      )
      if (!next) {
        next = { kind: 'folder', name, path, children: [], findings: 0, highest: null }
        folder.children.push(next)
      }
      folder = next
    })
    folder.children.push({
      kind: 'file',
      name: parts[parts.length - 1] ?? entry.path,
      path: entry.path,
      entry,
    })
  }
  total(root)
  sort(root)
  return root
}

function total(folder: FolderNode): void {
  for (const child of folder.children) {
    if (child.kind === 'folder') {
      total(child)
      folder.findings += child.findings
      folder.highest = higher(folder.highest, child.highest)
    } else {
      folder.findings += child.entry.findings
      folder.highest = higher(folder.highest, child.entry.highest_severity)
    }
  }
}

function sort(folder: FolderNode): void {
  folder.children.sort((a, b) =>
    a.kind === b.kind ? a.name.localeCompare(b.name) : a.kind === 'folder' ? -1 : 1,
  )
  for (const child of folder.children) if (child.kind === 'folder') sort(child)
}

/** The folders on the way to `path`, so the explorer can open them. */
export function ancestors(path: string): string[] {
  const parts = path.split('/').slice(0, -1)
  return parts.map((_, index) => parts.slice(0, index + 1).join('/'))
}
