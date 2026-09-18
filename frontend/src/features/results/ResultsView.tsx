import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useRef, useState } from 'react'
import { toast } from 'sonner'

import { CodeViewer } from '@/features/results/CodeViewer'
import { FileList } from '@/features/results/FileList'
import { FindingCard } from '@/features/results/FindingCard'
import { FindingFilters } from '@/features/results/FindingFilters'
import { ProvenanceTable } from '@/features/results/ProvenanceTable'
import { ReportLinks } from '@/features/results/ReportLinks'
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

const MIN_CONFIDENCE = 0.6

/** The results workspace: files, code with marks, and the findings beside it. */
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
  const visible = useMemo(() => applyFilter(all, filter, MIN_CONFIDENCE), [all, filter])
  const hiddenCount = all.filter((finding) => !isReported(finding, MIN_CONFIDENCE)).length
  const selected = visible.find((finding) => finding.id === selectedId) ?? visible[0] ?? null
  const filePath = selected?.file_path ?? filter.file ?? files.data?.files[0]?.path ?? null

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

  // Keep the selected card in sight, whether it was picked by a gutter mark or a key.
  const findingsPane = useRef<HTMLElement>(null)
  const selectedCardId = selected?.id
  useEffect(() => {
    const card = selectedCardId && document.getElementById(`finding-${selectedCardId}`)
    if (card && findingsPane.current) revealWithin(findingsPane.current, card, 'nearest')
  }, [selectedCardId])

  return (
    <div className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-[220px_1fr]">
        {detail.score && <ScoreCard score={detail.score} />}
        {detail.ai_summary && <SummaryCard summary={detail.ai_summary} />}
      </div>

      <ReportLinks scanId={scanId} />
      <FindingFilters filter={filter} onChange={setFilter} hiddenCount={hiddenCount} />

      <div className="grid gap-4 lg:h-[calc(100svh-5rem)] lg:grid-rows-[minmax(0,1fr)] lg:grid-cols-[200px_minmax(0,1fr)_minmax(0,26rem)]">
        <FileList
          files={files.data?.files ?? []}
          skipped={files.data?.skipped ?? []}
          selected={filePath}
          onSelect={(path) => setFilter({ ...filter, file: path })}
        />

        <section
          className="panel flex max-h-[70svh] min-h-64 flex-col overflow-hidden p-0 lg:max-h-none"
          aria-label="Code"
        >
          <h2 className="border-line path border-b px-3 py-2 text-[13px]">
            {filePath ?? 'No file selected'}
          </h2>
          {file.data ? (
            <CodeViewer
              content={file.data.content}
              language={file.data.language}
              findings={visible.filter((finding) => finding.file_path === filePath)}
              selectedId={selected?.id ?? null}
              onSelect={(finding) => setSelectedId(finding.id)}
            />
          ) : (
            <p className="text-muted p-3 text-[13px]">
              {filePath ? 'Loading…' : 'Pick a file to read it here.'}
            </p>
          )}
        </section>

        <section
          ref={findingsPane}
          className="space-y-2 lg:min-h-0 lg:overflow-y-auto lg:pr-1 motion-safe:scroll-smooth"
          aria-label="Findings"
        >
          <h2 className="bg-ink sticky top-0 z-10 py-0.5 text-[18px]">
            {visible.length} finding{visible.length === 1 ? '' : 's'}
          </h2>
          {visible.map((finding) => (
            <FindingCard
              key={finding.id}
              finding={finding}
              selected={selected?.id === finding.id}
              onSelect={() => setSelectedId(finding.id)}
              onDecide={(status) => decide.mutate({ finding, status })}
            />
          ))}
          {visible.length === 0 && (
            <p className="text-muted text-[13px]">Nothing matches these filters.</p>
          )}
        </section>
      </div>

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
