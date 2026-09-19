import Prism from 'prismjs'
import 'prismjs/components/prism-python'
import 'prismjs/components/prism-javascript'
import 'prismjs/components/prism-typescript'
import 'prismjs/components/prism-java'
import 'prismjs/components/prism-go'
import { Fragment, useEffect, useMemo, useRef, useState, type RefObject } from 'react'

import { SeverityChip } from '@/components/SeverityChip'
import type { Finding } from '@/lib/api'
import { revealWithin } from '@/lib/scroll'
import { SEVERITY_DOT, SEVERITY_EDGE, compareFindings, isModel } from '@/lib/severity'

const GRAMMARS: Record<string, string> = {
  python: 'python',
  javascript: 'javascript',
  typescript: 'typescript',
  java: 'java',
  go: 'go',
}

/**
 * Read-only code with severity marks in the gutter and on an overview ruler. The selected
 * finding's lines are highlighted and its note sits under them, as a review comment does.
 */
export function CodeViewer({
  content,
  language,
  findings,
  selectedId,
  wrap = false,
  onSelect,
}: {
  content: string
  language: string | null
  findings: Finding[]
  selectedId: string | null
  wrap?: boolean
  onSelect: (finding: Finding) => void
}) {
  const container = useRef<HTMLDivElement>(null)
  const paneWidth = usePaneWidth(container)
  const firstReveal = useRef(true)
  const selected = findings.find((finding) => finding.id === selectedId)

  const lines = useMemo(() => {
    const name = language ? GRAMMARS[language] : undefined
    const grammar = name ? Prism.languages[name] : undefined
    const html = name && grammar ? Prism.highlight(content, grammar, name) : escapeHtml(content)
    return html.replace(/\n$/, '').split('\n')
  }, [content, language])

  const marks = useMemo(() => {
    const byLine = new Map<number, Finding[]>()
    for (const finding of findings) {
      byLine.set(finding.start_line, [...(byLine.get(finding.start_line) ?? []), finding])
    }
    for (const list of byLine.values()) list.sort(compareFindings)
    return byLine
  }, [findings])

  // Land on the selected lines at once when a file opens; glide between findings after that.
  useEffect(() => {
    if (!selected || !container.current) return
    const row = container.current.querySelector<HTMLElement>(`[data-line="${selected.start_line}"]`)
    if (row) revealWithin(container.current, row, 'center', firstReveal.current)
    firstReveal.current = false
  }, [selected, lines])

  const selectedEnd = selected ? Math.max(selected.end_line, selected.start_line) : 0
  const noteLine = selected ? Math.min(selectedEnd, lines.length) : 0

  return (
    <div className="relative flex min-h-0 flex-1">
      <div
        ref={container}
        className="code bg-surface min-h-0 flex-1 overflow-auto overscroll-contain font-mono text-[13px] leading-[22px] motion-safe:scroll-smooth"
      >
        <table className={`border-collapse ${wrap ? 'w-full table-fixed' : 'min-w-full'}`}>
          <colgroup>
            <col className="w-7" />
            <col className="w-12" />
            <col />
          </colgroup>
          <tbody>
            {lines.map((line, index) => {
              const number = index + 1
              const lineFindings = marks.get(number) ?? []
              const [first] = lineFindings
              const inSelection =
                selected !== undefined && number >= selected.start_line && number <= selectedEnd
              const rowTone = inSelection ? 'bg-accent-soft' : 'bg-surface group-hover:bg-subtle'
              return (
                <Fragment key={number}>
                  <tr data-line={number} className="group">
                    <td
                      className={`sticky left-0 z-[1] w-7 min-w-7 pl-2 align-top transition-colors select-none ${rowTone}`}
                    >
                      {first && (
                        <button
                          type="button"
                          onClick={() => onSelect(first)}
                          title={lineFindings.map((finding) => finding.title).join('\n')}
                          className="grid h-[22px] w-4 cursor-pointer place-items-center"
                        >
                          <span
                            className={`ease-spring block size-2 rounded-full transition-transform duration-300 hover:scale-150 ${SEVERITY_DOT[first.severity]} ${
                              first.id === selectedId ? 'ring-accent/35 scale-125 ring-[3px]' : ''
                            }`}
                          />
                          <span className="sr-only">
                            {lineFindings.length} finding{lineFindings.length === 1 ? '' : 's'} on
                            line {number}
                          </span>
                        </button>
                      )}
                    </td>
                    <td
                      className={`sticky left-7 z-[1] w-12 min-w-12 pr-4 text-right align-top tabular-nums transition-colors select-none ${rowTone} ${
                        inSelection ? 'text-accent-text font-medium' : 'text-faint'
                      }`}
                    >
                      {number}
                    </td>
                    <td
                      className={`pr-8 align-top transition-colors ${rowTone} ${
                        wrap ? 'break-words whitespace-pre-wrap' : 'whitespace-pre'
                      }`}
                      // Prism escapes the code it highlights; plain text is escaped below.
                      dangerouslySetInnerHTML={{ __html: line || ' ' }}
                    />
                  </tr>
                  {selected && number === noteLine && (
                    <tr>
                      <td colSpan={3} className="bg-surface sticky left-0 py-2 pr-4 pl-[76px]">
                        <Annotation
                          finding={selected}
                          maxWidth={paneWidth ? Math.min(672, paneWidth - 96) : undefined}
                        />
                      </td>
                    </tr>
                  )}
                </Fragment>
              )
            })}
          </tbody>
        </table>
      </div>
      <OverviewRuler
        lines={lines.length}
        findings={findings}
        selectedId={selectedId}
        onSelect={onSelect}
      />
    </div>
  )
}

/** Where the findings sit in the whole file, like an editor's scrollbar marks. */
function OverviewRuler({
  lines,
  findings,
  selectedId,
  onSelect,
}: {
  lines: number
  findings: Finding[]
  selectedId: string | null
  onSelect: (finding: Finding) => void
}) {
  if (findings.length === 0 || lines === 0) return null
  return (
    <div
      aria-label="Findings in this file"
      className="border-line bg-subtle/40 relative w-3 shrink-0 border-l"
    >
      {[...findings]
        .sort(compareFindings)
        .reverse()
        .map((finding) => {
          const top = ((finding.start_line - 1) / Math.max(1, lines)) * 100
          const active = finding.id === selectedId
          return (
            <button
              key={finding.id}
              type="button"
              onClick={() => onSelect(finding)}
              title={`Line ${finding.start_line}: ${finding.title}`}
              style={{ top: `calc(${top}% + 2px)` }}
              className={`absolute left-1/2 h-1 -translate-x-1/2 cursor-pointer rounded-full transition-all duration-200 ${SEVERITY_DOT[finding.severity]} ${
                active
                  ? 'ring-accent/40 w-2.5 ring-2'
                  : 'w-1.5 opacity-80 hover:w-2.5 hover:opacity-100'
              }`}
            >
              <span className="sr-only">
                Line {finding.start_line}: {finding.title}
              </span>
            </button>
          )
        })}
    </div>
  )
}

/** The pane's visible width, so a note under the code fits it however long the lines are. */
function usePaneWidth(ref: RefObject<HTMLDivElement | null>): number | null {
  const [width, setWidth] = useState<number | null>(null)
  useEffect(() => {
    const element = ref.current
    if (!element || typeof ResizeObserver === 'undefined') return
    const observer = new ResizeObserver(([entry]) => {
      if (entry) setWidth(entry.contentRect.width)
    })
    observer.observe(element)
    return () => observer.disconnect()
  }, [ref])
  return width
}

function Annotation({ finding, maxWidth }: { finding: Finding; maxWidth?: number }) {
  const lines =
    finding.end_line > finding.start_line
      ? `Lines ${finding.start_line}–${finding.end_line}`
      : `Line ${finding.start_line}`
  return (
    <div
      key={finding.id}
      style={{ maxWidth }}
      className={`border-line bg-elevated rise shadow-lift max-w-2xl rounded-[10px] border border-l-[3px] px-3.5 py-3 font-sans whitespace-normal ${SEVERITY_EDGE[finding.severity]}`}
    >
      <div className="flex flex-wrap items-center gap-2">
        <SeverityChip severity={finding.severity} />
        <span className="min-w-0 flex-1 text-[13px] font-medium">{finding.title}</span>
        <span className="text-faint text-[11.5px]">{lines}</span>
      </div>
      {finding.message.trim() !== finding.title.trim() && (
        <p className="text-muted mt-1.5 text-[12.5px] leading-relaxed">{finding.message}</p>
      )}
      <div className="mt-2 flex flex-wrap items-center gap-1">
        {finding.sources.map((source) => (
          <span
            key={source}
            className={`mono rounded-[4px] border px-1.5 text-[10.5px] leading-[17px] ${
              isModel(source)
                ? 'border-accent/25 bg-accent-soft text-accent-text'
                : 'border-line bg-subtle text-muted'
            }`}
          >
            {source}
          </span>
        ))}
        {finding.cwe && <span className="text-faint mono ml-1 text-[10.5px]">{finding.cwe}</span>}
      </div>
    </div>
  )
}

function escapeHtml(text: string): string {
  return text
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
}
