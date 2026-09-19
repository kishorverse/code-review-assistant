import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ScanSearch, SearchX } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { toast } from 'sonner'

import { CodeViewer } from '@/features/results/CodeViewer'
import { FileList } from '@/features/results/FileList'
import { FindingCard } from '@/features/results/FindingCard'
import { FindingFilters } from '@/features/results/FindingFilters'
import { FindingsOverview } from '@/features/results/FindingsOverview'
import { ProvenanceTable } from '@/features/results/ProvenanceTable'
import { ScoreCard } from '@/features/results/ScoreCard'
import { SummaryCard } from '@/features/results/SummaryCard'
import {
  decideFinding,
  getFile,
  getFiles,
  listFindings,
  type Decision,
  type Finding,
  type ScanDetail,
} from '@/lib/api'
import { EMPTY_FILTER, applyFilter, isReported } from '@/lib/filters'
import { revealWithin } from '@/lib/scroll'
import { compareFindings } from '@/lib/severity'
import { stagger } from '@/lib/utils'

const MIN_CONFIDENCE = 0.6

/** The results workspace: an overview, then files, code with marks, and the findings. */
export function ResultsView({ scanId, detail }: { scanId: string; detail: ScanDetail }) {
  const queryClient = useQueryClient()
  const [filter, setFilter] = useState(EMPTY_FILTER)
  const [selectedId, setSelectedId] = useState<string | null>(null)

  const findings = useQuery({
    queryKey: ['findings', scanId],
    queryFn: () => listFindings(scanId),
  })
  const files = useQuery({ queryKey: ['files', scanId], queryFn: () => getFiles(scanId) })

  const all = useMemo(() => [...(findings.data ?? [])].sort(compareFindings), [findings.data])
  const reported = useMemo(
    () => all.filter((finding) => isReported(finding, MIN_CONFIDENCE)),
    [all],
  )
  const visible = useMemo(() => applyFilter(all, filter, MIN_CONFIDENCE), [all, filter])
  const hiddenCount = all.length - reported.length
  const selected = visible.find((finding) => finding.id === selectedId) ?? visible[0] ?? null
  const filePath = selected?.file_path ?? filter.file ?? files.data?.files[0]?.path ?? null
  const fileEntry = files.data?.files.find((entry) => entry.path === filePath)

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

  return (
    <div className="space-y-5">
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-[300px_300px_minmax(0,1fr)]">
        {detail.score && <ScoreCard score={detail.score} />}
        <FindingsOverview reported={reported} summary={detail.summary} />
        <div className="md:col-span-2 xl:col-span-1">
          {detail.ai_summary ? (
            <SummaryCard summary={detail.ai_summary} />
          ) : (
            <section className="rise panel flex h-full flex-col px-5 py-4.5" style={stagger(2)}>
              <h2 className="eyebrow">Summary</h2>
              <div className="flex flex-1 flex-col items-center justify-center gap-3 py-6 text-center">
                <span className="border-line bg-subtle text-faint grid size-10 place-items-center rounded-xl border">
                  <ScanSearch aria-hidden className="size-4.5" />
                </span>
                <p className="text-muted max-w-xs text-[13px] leading-relaxed">
                  No model summary for this review: it ran the static analyzers only.
                </p>
              </div>
            </section>
          )}
        </div>
      </div>

      <section
        className="rise panel shadow-lift overflow-hidden"
        style={stagger(3)}
        aria-label="Review workspace"
      >
        <div className="border-line bg-surface/80 border-b px-3 py-2.5 backdrop-blur">
          <FindingFilters filter={filter} onChange={setFilter} hiddenCount={hiddenCount} />
        </div>

        <div className="divide-line grid divide-y lg:h-[calc(100svh-8rem)] lg:min-h-[560px] lg:grid-cols-[232px_minmax(0,1fr)_380px] lg:grid-rows-[minmax(0,1fr)] lg:divide-x lg:divide-y-0 2xl:grid-cols-[260px_minmax(0,1fr)_440px]">
          <div className="bg-subtle/40 flex max-h-72 min-h-0 flex-col lg:max-h-none">
            <FileList
              files={files.data?.files ?? []}
              skipped={files.data?.skipped ?? []}
              selected={filePath}
              onSelect={(path) => setFilter({ ...filter, file: path })}
            />
          </div>

          <section
            className="flex max-h-[70svh] min-h-64 min-w-0 flex-col lg:max-h-none"
            aria-label="Code"
          >
            <header className="border-line flex h-11 shrink-0 items-center gap-3 border-b px-4">
              <span aria-hidden className="flex gap-1.5">
                <span className="bg-line-strong size-2.5 rounded-full" />
                <span className="bg-line-strong size-2.5 rounded-full" />
                <span className="bg-line-strong size-2.5 rounded-full" />
              </span>
              <h2
                key={filePath}
                className="fade-in mono min-w-0 truncate text-[12.5px] font-medium"
              >
                {filePath ?? 'No file selected'}
              </h2>
              {fileEntry && (
                <span className="text-faint ml-auto shrink-0 text-[11.5px]">
                  {[
                    fileEntry.language,
                    fileEntry.lines !== null ? `${fileEntry.lines} lines` : null,
                  ]
                    .filter(Boolean)
                    .join(' · ')}
                </span>
              )}
            </header>
            {file.data ? (
              <CodeViewer
                key={filePath}
                content={file.data.content}
                language={file.data.language}
                findings={visible.filter((finding) => finding.file_path === filePath)}
                selectedId={selected?.id ?? null}
                onSelect={(finding) => setSelectedId(finding.id)}
              />
            ) : (
              <div className="space-y-2 p-4" aria-live="polite">
                {filePath ? (
                  <>
                    <p className="sr-only">Loading…</p>
                    {[72, 54, 88, 40, 66, 58, 80].map((width, index) => (
                      <div
                        key={index}
                        className="shimmer bg-subtle h-3 rounded"
                        style={{ width: `${width}%` }}
                      />
                    ))}
                  </>
                ) : (
                  <p className="text-muted text-[13px]">Pick a file to read it here.</p>
                )}
              </div>
            )}
          </section>

          <section className="flex min-h-0 min-w-0 flex-col" aria-label="Findings">
            <header className="border-line flex h-11 shrink-0 items-center gap-2 border-b px-4">
              <h2 className="text-[12.5px] font-semibold">Findings</h2>
              <span className="bg-subtle text-muted rounded-full px-1.5 text-[11px] font-medium tabular-nums">
                {visible.length}
              </span>
            </header>
            <div
              ref={findingsPane}
              className="min-h-0 flex-1 overflow-y-auto motion-safe:scroll-smooth"
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
              {visible.length === 0 && findings.isSuccess && (
                <div className="fade-in px-6 py-16 text-center">
                  <span className="border-line bg-subtle mx-auto grid size-10 place-items-center rounded-xl border">
                    <SearchX aria-hidden className="text-faint size-4.5" />
                  </span>
                  <p className="text-muted mt-3 text-[13px]">
                    {all.length === 0
                      ? 'No findings. The code looks clean.'
                      : 'Nothing matches these filters.'}
                  </p>
                </div>
              )}
            </div>
          </section>
        </div>
      </section>

      <ProvenanceTable calls={detail.calls} />
    </div>
  )
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
