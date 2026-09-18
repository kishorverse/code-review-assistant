import Prism from 'prismjs'
import 'prismjs/components/prism-python'
import 'prismjs/components/prism-javascript'
import 'prismjs/components/prism-typescript'
import 'prismjs/components/prism-java'
import 'prismjs/components/prism-go'
import { useEffect, useMemo, useRef } from 'react'

import type { Finding } from '@/lib/api'
import { revealWithin } from '@/lib/scroll'
import { SEVERITY_DOT, compareFindings } from '@/lib/severity'

const GRAMMARS: Record<string, string> = {
  python: 'python',
  javascript: 'javascript',
  typescript: 'typescript',
  java: 'java',
  go: 'go',
}

/** Read-only code with severity marks in the gutter, as an editor marks a manuscript. */
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
    return html.split('\n')
  }, [content, language])

  const marks = useMemo(() => {
    const byLine = new Map<number, Finding[]>()
    for (const finding of findings) {
      byLine.set(finding.start_line, [...(byLine.get(finding.start_line) ?? []), finding])
    }
    return byLine
  }, [findings])

  useEffect(() => {
    if (!selected || !container.current) return
    const row = container.current.querySelector<HTMLElement>(`[data-line="${selected.start_line}"]`)
    if (row) revealWithin(container.current, row, 'center')
  }, [selected, lines])

  return (
    <div
      ref={container}
      className="code min-h-0 flex-1 overflow-auto font-mono text-[13px] leading-[1.6] motion-safe:scroll-smooth"
    >
      <table className="w-full border-collapse">
        <tbody>
          {lines.map((line, index) => {
            const number = index + 1
            const lineFindings = (marks.get(number) ?? []).sort(compareFindings)
            const [first] = lineFindings
            const inSelection =
              selected && number >= selected.start_line && number <= selected.end_line
            return (
              <tr
                key={number}
                data-line={number}
                className={inSelection ? 'bg-brand-soft' : undefined}
              >
                <td className="w-8 select-none pr-1 align-middle">
                  {first && (
                    <button
                      type="button"
                      onClick={() => onSelect(first)}
                      title={lineFindings.map((finding) => finding.title).join('\n')}
                      className="mark-in mx-auto block size-2 rounded-full"
                    >
                      <span
                        className={`block size-2 rounded-full ${SEVERITY_DOT[first.severity]}`}
                      />
                      <span className="sr-only">
                        {lineFindings.length} finding(s) on line {number}
                      </span>
                    </button>
                  )}
                </td>
                <td className="text-muted w-10 select-none pr-3 text-right align-middle tabular-nums">
                  {number}
                </td>
                <td
                  className="whitespace-pre align-middle"
                  // Prism escapes the code it highlights; plain text is escaped above.
                  dangerouslySetInnerHTML={{ __html: line || ' ' }}
                />
              </tr>
            )
          })}
        </tbody>
      </table>
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
