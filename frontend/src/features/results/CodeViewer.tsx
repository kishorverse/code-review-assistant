import Prism from 'prismjs'
import 'prismjs/components/prism-python'
import 'prismjs/components/prism-javascript'
import 'prismjs/components/prism-typescript'
import 'prismjs/components/prism-java'
import 'prismjs/components/prism-go'
import { Fragment, useEffect, useMemo, useRef } from 'react'

import { SeverityChip } from '@/components/SeverityChip'
import type { Finding } from '@/lib/api'
import { revealWithin } from '@/lib/scroll'
import { SEVERITY_DOT, SEVERITY_EDGE, compareFindings } from '@/lib/severity'

const GRAMMARS: Record<string, string> = {
  python: 'python',
  javascript: 'javascript',
  typescript: 'typescript',
  java: 'java',
  go: 'go',
}

/**
 * Read-only code with severity marks in the gutter. The selected finding's lines are
 * highlighted and its note sits under them, as a review comment does.
 */
export function CodeViewer({
  content,
  language,
  findings,
  selectedId,
  onSelect,
}: {
  content: string
  language: string | null
  findings: Finding[]
  selectedId: string | null
  onSelect: (finding: Finding) => void
}) {
  const container = useRef<HTMLDivElement>(null)
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

  useEffect(() => {
    if (!selected || !container.current) return
    const row = container.current.querySelector<HTMLElement>(`[data-line="${selected.start_line}"]`)
    if (row) revealWithin(container.current, row, 'center')
  }, [selected, lines])

  const noteLine = selected
    ? Math.min(Math.max(selected.end_line, selected.start_line), lines.length)
    : 0

  return (
    <div
      ref={container}
      className="code bg-surface min-h-0 flex-1 overflow-auto font-mono text-[12.5px] leading-5 motion-safe:scroll-smooth"
    >
      <table className="min-w-full border-collapse">
        <tbody>
          {lines.map((line, index) => {
            const number = index + 1
            const lineFindings = marks.get(number) ?? []
            const [first] = lineFindings
            const inSelection =
              selected !== undefined &&
              number >= selected.start_line &&
              number <= Math.max(selected.end_line, selected.start_line)
            return (
              <Fragment key={number}>
                <tr
                  data-line={number}
                  className={`transition-colors duration-300 ${inSelection ? 'bg-accent-soft' : 'hover:bg-subtle/60'}`}
                >
                  <td className="w-6 pl-1.5 align-top select-none">
                    {first && (
                      <button
                        type="button"
                        onClick={() => onSelect(first)}
                        title={lineFindings.map((finding) => finding.title).join('\n')}
                        className="grid h-5 w-4 cursor-pointer place-items-center"
                      >
                        <span
                          className={`block size-2 rounded-full transition-transform duration-300 ease-spring hover:scale-150 ${SEVERITY_DOT[first.severity]} ${
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
                    className={`w-12 pr-4 text-right align-top tabular-nums select-none ${
                      inSelection ? 'text-accent-text' : 'text-faint'
                    }`}
                  >
                    {number}
                  </td>
                  <td
                    className="pr-6 align-top whitespace-pre"
                    // Prism escapes the code it highlights; plain text is escaped below.
                    dangerouslySetInnerHTML={{ __html: line || ' ' }}
                  />
                </tr>
                {selected && number === noteLine && (
                  <tr>
                    <td colSpan={3} className="px-3 py-2">
                      <Annotation finding={selected} />
                    </td>
                  </tr>
                )}
              </Fragment>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function Annotation({ finding }: { finding: Finding }) {
  const lines =
    finding.end_line > finding.start_line
      ? `Lines ${finding.start_line}–${finding.end_line}`
      : `Line ${finding.start_line}`
  return (
    <div
      key={finding.id}
      className={`border-line bg-elevated rise shadow-lift max-w-2xl rounded-[10px] border border-l-[3px] px-3.5 py-3 font-sans whitespace-normal ${SEVERITY_EDGE[finding.severity]}`}
    >
      <div className="flex flex-wrap items-center gap-2">
        <SeverityChip severity={finding.severity} />
        <span className="text-[13px] font-medium">{finding.title}</span>
        <span className="text-faint ml-auto text-[11.5px]">{lines}</span>
      </div>
      {finding.message.trim() !== finding.title.trim() && (
        <p className="text-muted mt-1.5 text-[12.5px] leading-relaxed">{finding.message}</p>
      )}
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
