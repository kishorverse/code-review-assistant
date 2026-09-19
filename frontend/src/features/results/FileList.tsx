import { ChevronRight, FileCode2, FileText, Folder, FolderOpen, PanelLeftClose } from 'lucide-react'
import { useMemo, useState } from 'react'

import type { FileEntry, Severity, SkippedFile } from '@/lib/api'
import { ancestors, buildFileTree, type FolderNode, type TreeNode } from '@/lib/fileTree'
import { SEVERITY_DOT } from '@/lib/severity'

const CODE_LANGUAGES = ['python', 'javascript', 'typescript', 'java', 'go']

/** The scan's files as a tree, like an editor's explorer, with findings per file and folder. */
export function FileList({
  files,
  skipped,
  selected,
  onSelect,
  onCollapse,
}: {
  files: FileEntry[]
  skipped: SkippedFile[]
  selected: string | null
  onSelect: (path: string) => void
  onCollapse?: () => void
}) {
  const tree = useMemo(() => buildFileTree(files), [files])
  const [closed, setClosed] = useState<Set<string>>(() => new Set())

  // Whatever is selected, from the explorer or a finding, stays visible: when the selection
  // changes, open the folders above it. Adjusting state here, not in an effect, avoids a
  // render with the file hidden.
  const [revealed, setRevealed] = useState(selected)
  if (revealed !== selected) {
    setRevealed(selected)
    const needed = selected ? ancestors(selected) : []
    if (needed.some((path) => closed.has(path))) {
      setClosed(new Set([...closed].filter((path) => !needed.includes(path))))
    }
  }

  const toggle = (path: string) =>
    setClosed((current) => {
      const next = new Set(current)
      if (next.has(path)) next.delete(path)
      else next.add(path)
      return next
    })

  return (
    <nav className="flex min-h-0 flex-1 flex-col" aria-label="Files">
      <div className="flex h-10 shrink-0 items-center gap-2 pr-2 pl-3.5">
        <h2 className="eyebrow">Explorer</h2>
        <span className="text-faint text-[11px] tabular-nums">{files.length}</span>
        {onCollapse && (
          <button
            type="button"
            onClick={onCollapse}
            title="Hide the explorer"
            className="text-faint hover:text-text hover:bg-hover rounded-control ml-auto grid size-6 cursor-pointer place-items-center transition-colors"
          >
            <PanelLeftClose aria-hidden className="size-3.5" />
          </button>
        )}
      </div>
      <ul
        role="tree"
        aria-label="Project files"
        className="min-h-0 flex-1 overflow-y-auto overscroll-contain pb-2"
      >
        <TreeChildren
          folder={tree}
          depth={0}
          closed={closed}
          selected={selected}
          onToggle={toggle}
          onSelect={onSelect}
        />
      </ul>
      {skipped.length > 0 && (
        <details className="border-line text-muted group shrink-0 border-t px-3.5 py-2 text-[12px]">
          <summary className="flex cursor-pointer list-none items-center gap-1.5 select-none">
            <ChevronRight
              aria-hidden
              className="size-3 transition-transform duration-200 group-open:rotate-90"
            />
            {skipped.length} files skipped
          </summary>
          <ul className="animate-expand mt-1.5 max-h-40 space-y-1 overflow-y-auto">
            {skipped.map((file) => (
              <li key={file.path} className="flex gap-2">
                <span className="mono min-w-0 flex-1 truncate">{file.path}</span>
                <span className="text-faint shrink-0">{file.reason.replaceAll('_', ' ')}</span>
              </li>
            ))}
          </ul>
        </details>
      )}
    </nav>
  )
}

function TreeChildren({
  folder,
  depth,
  closed,
  selected,
  onToggle,
  onSelect,
}: {
  folder: FolderNode
  depth: number
  closed: Set<string>
  selected: string | null
  onToggle: (path: string) => void
  onSelect: (path: string) => void
}) {
  return (
    <>
      {folder.children.map((node) => (
        <TreeRow
          key={node.path}
          node={node}
          depth={depth}
          closed={closed}
          selected={selected}
          onToggle={onToggle}
          onSelect={onSelect}
        />
      ))}
    </>
  )
}

function TreeRow({
  node,
  depth,
  closed,
  selected,
  onToggle,
  onSelect,
}: {
  node: TreeNode
  depth: number
  closed: Set<string>
  selected: string | null
  onToggle: (path: string) => void
  onSelect: (path: string) => void
}) {
  const indent = { paddingLeft: 10 + depth * 14 }

  if (node.kind === 'folder') {
    const open = !closed.has(node.path)
    const Icon = open ? FolderOpen : Folder
    return (
      <li role="treeitem" aria-expanded={open} aria-selected={false}>
        <button
          type="button"
          onClick={() => onToggle(node.path)}
          style={indent}
          className="text-muted hover:bg-hover hover:text-text flex h-7 w-full cursor-pointer items-center gap-1.5 pr-3 text-left transition-colors"
        >
          <ChevronRight
            aria-hidden
            className={`size-3 shrink-0 transition-transform duration-200 ${open ? 'rotate-90' : ''}`}
          />
          <Icon aria-hidden className="text-accent-text/80 size-3.5 shrink-0" />
          <span className="min-w-0 flex-1 truncate text-[12.5px]">{node.name}</span>
          {!open && <Count findings={node.findings} highest={node.highest} />}
        </button>
        {open && (
          <ul role="group" className="fade-in">
            <TreeChildren
              folder={node}
              depth={depth + 1}
              closed={closed}
              selected={selected}
              onToggle={onToggle}
              onSelect={onSelect}
            />
          </ul>
        )}
      </li>
    )
  }

  const active = selected === node.path
  const Icon =
    node.entry.language && CODE_LANGUAGES.includes(node.entry.language) ? FileCode2 : FileText
  return (
    <li role="treeitem" aria-selected={active}>
      <button
        type="button"
        onClick={() => onSelect(node.path)}
        title={node.path}
        style={{ paddingLeft: 10 + depth * 14 + 16 }}
        className={`relative flex h-7 w-full cursor-pointer items-center gap-1.5 pr-3 text-left transition-colors ${
          active ? 'bg-accent-soft text-text' : 'text-muted hover:bg-hover hover:text-text'
        }`}
      >
        <span
          aria-hidden
          className={`bg-accent absolute inset-y-0 left-0 w-[2px] transition-opacity ${active ? 'opacity-100' : 'opacity-0'}`}
        />
        <Icon
          aria-hidden
          className={`size-3.5 shrink-0 ${active ? 'text-accent-text' : 'opacity-70'}`}
        />
        <span
          className={`mono min-w-0 flex-1 truncate text-[12.5px] ${active ? 'font-medium' : ''}`}
        >
          {node.name}
        </span>
        <Count findings={node.entry.findings} highest={node.entry.highest_severity} />
      </button>
    </li>
  )
}

function Count({ findings, highest }: { findings: number; highest: Severity | null }) {
  if (findings === 0) return null
  return (
    <span className="text-faint flex shrink-0 items-center gap-1 text-[11px] tabular-nums">
      {highest && <span aria-hidden className={`size-1.5 rounded-full ${SEVERITY_DOT[highest]}`} />}
      {findings}
      <span className="sr-only"> findings</span>
    </span>
  )
}
