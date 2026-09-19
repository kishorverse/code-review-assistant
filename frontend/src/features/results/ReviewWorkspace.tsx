import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  ChevronDown,
  ChevronRight,
  CircleCheck,
  ChevronUp,
  FileCode2,
  FileSearch,
  PanelLeftOpen,
  SearchX,
  WrapText,
} from 'lucide-react'
import { useEffect, useMemo, useRef, useState, type CSSProperties, type ReactNode } from 'react'
import { toast } from 'sonner'

import { CodeViewer } from '@/features/results/CodeViewer'
import { FileList } from '@/features/results/FileList'
import { FindingCard } from '@/features/results/FindingCard'
import { FindingFilters } from '@/features/results/FindingFilters'
import { decideFinding, getFile, type Decision, type FileTree, type Finding } from '@/lib/api'
import type { FindingFilter } from '@/lib/filters'
import { useResizablePane } from '@/lib/panes'
import { revealWithin } from '@/lib/scroll'
import { SEVERITIES, SEVERITY_DOT, SEVERITY_LABEL, countBySeverity } from '@/lib/severity'

const EXPLORER_KEY = 'margin-explorer-open'
const WRAP_KEY = 'margin-code-wrap'

/**
 * The review as an editor: files on the left, the code in the middle, the findings on the
 * right, and a status bar. Picking a finding anywhere opens its file at its lines.
 */
export function ReviewWorkspace({
  scanId,
  files,
  visible,
  total,
  hiddenCount,
  loaded,
  filter,
  onFilter,
}: {
  scanId: string
  files: FileTree | undefined
  visible: Finding[]
  total: number
  hiddenCount: number
  loaded: boolean
  filter: FindingFilter
  onFilter: (filter: FindingFilter) => void
}) {
  const queryClient = useQueryClient()
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [explorerOpen, setExplorerOpen] = useStoredFlag(EXPLORER_KEY, true)
  const [wrap, setWrap] = useStoredFlag(WRAP_KEY, true)
  const pane = useResizablePane({
    key: 'margin-findings-width',
    initial: 400,
    min: 320,
    max: 640,
    edge: 'left',
  })

  // A single file needs no explorer; the code gets the width instead.
  const hasTree = (files?.files.length ?? 0) > 1
  const showExplorer = hasTree && explorerOpen

  const selected = visible.find((finding) => finding.id === selectedId) ?? visible[0] ?? null
  const filePath = selected?.file_path ?? filter.file ?? files?.files[0]?.path ?? null
  const fileEntry = files?.files.find((entry) => entry.path === filePath)
  const inFile = useMemo(
    () =>
      visible
        .filter((finding) => finding.file_path === filePath)
        .sort((a, b) => a.start_line - b.start_line),
    [visible, filePath],
  )

  const file = useQuery({
    queryKey: ['file', scanId, filePath],
    queryFn: () => getFile(scanId, filePath as string),
    enabled: filePath !== null,
  })

  const decide = useMutation({
    mutationFn: ({ finding, status }: { finding: Finding; status: Decision }) =>
      decideFinding(scanId, finding.id, status),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['findings', scanId] })
      void queryClient.invalidateQueries({ queryKey: ['scan', scanId] })
      void queryClient.invalidateQueries({ queryKey: ['files', scanId] })
    },
    onError: () => toast.error('That decision could not be saved.'),
  })

  useKeyboardNavigation(visible, selected, setSelectedId)

  // Keep the selected finding in sight, whether it was picked by a gutter mark or a key.
  const findingsPane = useRef<HTMLDivElement>(null)
  const selectedCardId = selected?.id
  useEffect(() => {
    const card = selectedCardId && document.getElementById(`finding-${selectedCardId}`)
    if (card && findingsPane.current) revealWithin(findingsPane.current, card, 'nearest')
  }, [selectedCardId])

  const position = selected ? inFile.findIndex((finding) => finding.id === selected.id) : -1
  const step = (direction: 1 | -1) => {
    const next = inFile[position + direction]
    if (next) setSelectedId(next.id)
  }

  return (
    <section
      aria-label="Review workspace"
      className="panel shadow-lift flex min-h-0 flex-1 flex-col overflow-hidden"
    >
      <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
        {showExplorer && (
          <aside className="border-line bg-subtle/40 fade-in flex max-h-64 min-h-0 shrink-0 flex-col border-b lg:max-h-none lg:w-56 lg:border-r lg:border-b-0 xl:w-60">
            <FileList
              files={files?.files ?? []}
              skipped={files?.skipped ?? []}
              selected={filePath}
              onSelect={(path) => {
                onFilter({ ...filter, file: path })
                setSelectedId(null)
              }}
              onCollapse={() => setExplorerOpen(false)}
            />
          </aside>
        )}

        <section
          aria-label="Code"
          className="flex h-[65svh] min-h-0 min-w-0 flex-1 flex-col lg:h-auto"
        >
          <div className="border-line bg-subtle/40 flex h-10 shrink-0 items-stretch border-b">
            {hasTree && !explorerOpen && (
              <ToolbarButton label="Show the explorer" onClick={() => setExplorerOpen(true)}>
                <PanelLeftOpen aria-hidden className="size-3.5" />
              </ToolbarButton>
            )}
            {filePath && (
              <div
                key={filePath}
                className="border-line bg-surface fade-in relative flex min-w-0 items-center gap-2 border-r px-3.5 text-[12.5px]"
              >
                <span aria-hidden className="bg-accent absolute inset-x-0 top-0 h-[2px]" />
                <FileCode2 aria-hidden className="text-accent-text size-3.5 shrink-0" />
                <span className="mono truncate font-medium">
                  {filePath.slice(filePath.lastIndexOf('/') + 1)}
                </span>
                {inFile.length > 0 && (
                  <span className="bg-subtle text-muted rounded-full px-1.5 text-[10.5px] font-medium tabular-nums">
                    {inFile.length}
                  </span>
                )}
              </div>
            )}
            <div className="ml-auto flex items-center gap-0.5 pr-1.5">
              {inFile.length > 0 && (
                <>
                  <span className="text-faint mr-1 hidden text-[11.5px] tabular-nums sm:inline">
                    {position >= 0 ? `${position + 1} of ${inFile.length}` : `${inFile.length}`} in
                    file
                  </span>
                  <ToolbarButton
                    label="Previous finding in this file"
                    disabled={position <= 0}
                    onClick={() => step(-1)}
                  >
                    <ChevronUp aria-hidden className="size-3.5" />
                  </ToolbarButton>
                  <ToolbarButton
                    label="Next finding in this file"
                    disabled={position < 0 || position >= inFile.length - 1}
                    onClick={() => step(1)}
                  >
                    <ChevronDown aria-hidden className="size-3.5" />
                  </ToolbarButton>
                  <span aria-hidden className="bg-line mx-1 h-4 w-px" />
                </>
              )}
              <ToolbarButton
                label={wrap ? 'Stop wrapping long lines' : 'Wrap long lines'}
                pressed={wrap}
                onClick={() => setWrap(!wrap)}
              >
                <WrapText aria-hidden className="size-3.5" />
              </ToolbarButton>
            </div>
          </div>

          {filePath && (
            <Breadcrumbs path={filePath} language={fileEntry?.language} lines={fileEntry?.lines} />
          )}

          {file.data ? (
            <CodeViewer
              key={filePath}
              content={file.data.content}
              language={file.data.language}
              findings={inFile}
              selectedId={selected?.id ?? null}
              wrap={wrap}
              onSelect={(finding) => setSelectedId(finding.id)}
            />
          ) : filePath ? (
            <div className="space-y-2.5 p-5" aria-live="polite">
              <p className="sr-only">Loading…</p>
              {[72, 54, 88, 40, 66, 58, 80, 46].map((width, index) => (
                <div key={index} className="flex items-center gap-4">
                  <div className="shimmer bg-subtle h-3 w-6 rounded" />
                  <div className="shimmer bg-subtle h-3 rounded" style={{ width: `${width}%` }} />
                </div>
              ))}
            </div>
          ) : (
            <Empty icon={FileSearch}>Pick a file to read it here.</Empty>
          )}
        </section>

        <div
          {...pane.handleProps}
          aria-label="Resize the findings panel"
          title="Drag to resize · double-click to reset"
          className="group relative z-10 hidden w-0 cursor-col-resize outline-none lg:block"
        >
          <span
            className={`absolute inset-y-0 -left-[3px] w-[6px] transition-colors group-hover:bg-accent/25 group-focus-visible:bg-accent/40 ${
              pane.dragging ? 'bg-accent/40' : ''
            }`}
          />
        </div>

        <section
          aria-label="Findings"
          style={{ '--pane-w': `${pane.width}px` } as CSSProperties}
          className="border-line flex min-h-0 min-w-0 shrink-0 flex-col border-t lg:w-[var(--pane-w)] lg:border-t-0 lg:border-l"
        >
          <header className="border-line shrink-0 space-y-2.5 border-b px-3.5 pt-3 pb-3">
            <div className="flex items-center gap-2">
              <h2 className="text-[13px] font-semibold">Findings</h2>
              <span className="bg-subtle text-muted rounded-full px-1.5 text-[11px] font-medium tabular-nums">
                {visible.length}
              </span>
              {visible.length !== total && (
                <span className="text-faint text-[11.5px]">of {total}</span>
              )}
            </div>
            <FindingFilters filter={filter} onChange={onFilter} hiddenCount={hiddenCount} />
          </header>
          <div
            ref={findingsPane}
            className="flex max-h-[70svh] min-h-0 flex-1 flex-col overflow-y-auto overscroll-contain motion-safe:scroll-smooth lg:max-h-none"
          >
            {visible.map((finding) => (
              <FindingCard
                key={finding.id}
                finding={finding}
                selected={selected?.id === finding.id}
                onSelect={() => setSelectedId(finding.id)}
                onDecide={(status) => decide.mutate({ finding, status })}
              />
            ))}
            {visible.length === 0 &&
              loaded &&
              (total === 0 ? (
                <Empty icon={CircleCheck} tone="success" title="No findings">
                  The analyzers and models found nothing to report in this code.
                </Empty>
              ) : (
                <Empty icon={SearchX} title="Nothing matches">
                  Try another search, or reset the filters.
                </Empty>
              ))}
          </div>
        </section>
      </div>

      <StatusBar findings={visible} selected={selected} language={fileEntry?.language ?? null} />
    </section>
  )
}

function Breadcrumbs({
  path,
  language,
  lines,
}: {
  path: string
  language: string | null | undefined
  lines: number | null | undefined
}) {
  const parts = path.split('/')
  return (
    <div className="border-line text-faint flex h-8 shrink-0 items-center gap-1 border-b px-4 text-[11.5px]">
      <nav aria-label="File path" className="mono flex min-w-0 items-center gap-1 truncate">
        {parts.map((part, index) => (
          <span key={index} className="flex shrink-0 items-center gap-1 last:shrink">
            {index > 0 && <ChevronRight aria-hidden className="size-3 opacity-60" />}
            <span className={index === parts.length - 1 ? 'text-text truncate' : ''}>{part}</span>
          </span>
        ))}
      </nav>
      <span className="ml-auto shrink-0 pl-3">
        {[language, lines != null ? `${lines} lines` : null].filter(Boolean).join(' · ')}
      </span>
    </div>
  )
}

function StatusBar({
  findings,
  selected,
  language,
}: {
  findings: Finding[]
  selected: Finding | null
  language: string | null
}) {
  const counts = countBySeverity(findings)
  return (
    <footer className="border-line bg-subtle/70 text-muted flex h-7 shrink-0 items-center gap-4 overflow-hidden border-t px-3.5 text-[11px] whitespace-nowrap">
      <span className="flex items-center gap-3">
        {SEVERITIES.filter((severity) => counts[severity] > 0).map((severity) => (
          <span key={severity} className="flex items-center gap-1" title={SEVERITY_LABEL[severity]}>
            <span aria-hidden className={`size-1.5 rounded-full ${SEVERITY_DOT[severity]}`} />
            <span className="tabular-nums">{counts[severity]}</span>
            <span className="lowercase">{SEVERITY_LABEL[severity]}</span>
          </span>
        ))}
        {findings.length === 0 && <span>No findings shown</span>}
      </span>
      {selected && (
        <span className="mono hidden min-w-0 truncate md:inline">
          {selected.file_path} · Ln {selected.start_line}
          {selected.start_column ? `, Col ${selected.start_column}` : ''}
        </span>
      )}
      <span className="ml-auto hidden items-center gap-3 sm:flex">
        {language && <span className="capitalize">{language}</span>}
        <span className="flex items-center gap-1">
          <Kbd>j</Kbd>
          <Kbd>k</Kbd>
          <span>move</span>
        </span>
        <span className="flex items-center gap-1">
          <Kbd>n</Kbd>
          <span>new review</span>
        </span>
      </span>
    </footer>
  )
}

function Kbd({ children }: { children: ReactNode }) {
  return (
    <kbd className="border-line bg-surface rounded border px-1 font-sans text-[10px] leading-[14px]">
      {children}
    </kbd>
  )
}

function ToolbarButton({
  label,
  onClick,
  disabled,
  pressed,
  children,
}: {
  label: string
  onClick: () => void
  disabled?: boolean
  pressed?: boolean
  children: ReactNode
}) {
  return (
    <button
      type="button"
      title={label}
      aria-label={label}
      aria-pressed={pressed}
      disabled={disabled}
      onClick={onClick}
      className={`rounded-control my-auto grid size-7 shrink-0 cursor-pointer place-items-center transition-colors disabled:cursor-default disabled:opacity-35 ${
        pressed
          ? 'bg-accent-soft text-accent-text'
          : 'text-muted hover:bg-hover hover:text-text disabled:hover:bg-transparent'
      }`}
    >
      {children}
    </button>
  )
}

function Empty({
  icon: Icon,
  title,
  tone,
  children,
}: {
  icon: typeof SearchX
  title?: string
  tone?: 'success'
  children: ReactNode
}) {
  return (
    <div className="fade-in flex flex-1 flex-col items-center justify-center px-6 py-14 text-center">
      <span
        className={`grid size-11 place-items-center rounded-xl border ${
          tone === 'success'
            ? 'border-success/25 bg-success/10 text-success'
            : 'border-line bg-subtle text-faint'
        }`}
      >
        <Icon aria-hidden className="size-5" />
      </span>
      {title && <p className="mt-3.5 text-[14px] font-semibold">{title}</p>}
      <p className="text-muted mt-1 max-w-64 text-[13px] leading-relaxed">{children}</p>
    </div>
  )
}

/** A remembered on/off setting; storage can be unavailable, and then it isn't remembered. */
function useStoredFlag(key: string, initial: boolean): [boolean, (value: boolean) => void] {
  const [value, setValue] = useState(() => {
    try {
      const stored = localStorage.getItem(key)
      return stored === null ? initial : stored === '1'
    } catch {
      return initial
    }
  })
  const update = (next: boolean) => {
    setValue(next)
    try {
      localStorage.setItem(key, next ? '1' : '0')
    } catch {
      // Not remembered.
    }
  }
  return [value, update]
}

/** j and k move between findings, as in a pager. */
function useKeyboardNavigation(
  visible: Finding[],
  selected: Finding | null,
  select: (id: string) => void,
): void {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.target instanceof HTMLElement && event.target.closest('input, select, textarea')) {
        return
      }
      if (event.metaKey || event.ctrlKey || event.altKey) return
      if (event.key !== 'j' && event.key !== 'k') return
      const index = visible.findIndex((finding) => finding.id === selected?.id)
      const next = event.key === 'j' ? index + 1 : index - 1
      const finding = visible[Math.max(0, Math.min(visible.length - 1, next))]
      if (finding) select(finding.id)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [visible, selected, select])
}
