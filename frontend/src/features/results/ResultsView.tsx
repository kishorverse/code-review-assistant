import { useQuery } from '@tanstack/react-query'
import { Code2, Cpu, FileText, Maximize2, Minimize2 } from 'lucide-react'
import { Tabs } from 'radix-ui'
import { useEffect, useMemo, useRef, useState, type ReactNode, type RefObject } from 'react'

import { ModelsTab } from '@/features/results/ModelsTab'
import { ResultsOverview } from '@/features/results/ResultsOverview'
import { ReviewWorkspace } from '@/features/results/ReviewWorkspace'
import { SummaryTab } from '@/features/results/SummaryTab'
import { getFiles, listFindings, type ScanDetail } from '@/lib/api'
import { EMPTY_FILTER, applyFilter, isReported } from '@/lib/filters'
import { compareFindings } from '@/lib/severity'
import { stagger } from '@/lib/utils'

const MIN_CONFIDENCE = 0.6

type Tab = 'review' | 'summary' | 'models'

/** The results: the review at a glance, then the code review, the summary, or the models. */
export function ResultsView({ scanId, detail }: { scanId: string; detail: ScanDetail }) {
  const [tab, setTab] = useState<Tab>('review')
  const [filter, setFilter] = useState(EMPTY_FILTER)

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

  const sentinel = useRef<HTMLDivElement>(null)
  const [focused, toggleFocus] = useEditorFocus(sentinel)

  return (
    <div className="flex flex-col gap-3">
      <ResultsOverview
        detail={detail}
        reported={reported}
        onOpenSummary={() => setTab('summary')}
      />

      <Tabs.Root value={tab} onValueChange={(value) => setTab(value as Tab)}>
        {/* Marks where the tab bar sits in the page, before it sticks. */}
        <div ref={sentinel} aria-hidden />
        <div
          className="rise bg-canvas/90 border-line sticky top-0 z-20 -mx-4 mb-3 flex items-end gap-2 border-b px-4 backdrop-blur-md lg:-mx-6 lg:px-6"
          style={stagger(1)}
        >
          <Tabs.List aria-label="Results" className="flex min-w-0 flex-1 items-end gap-1">
            <TabTrigger value="review" icon={Code2} count={reported.length}>
              Review
            </TabTrigger>
            <TabTrigger value="summary" icon={FileText}>
              Summary
            </TabTrigger>
            <TabTrigger value="models" icon={Cpu} count={detail.calls.length}>
              Models
            </TabTrigger>
          </Tabs.List>
          <button
            type="button"
            onClick={toggleFocus}
            title={focused ? 'Show the overview (f)' : 'Give the review the whole screen (f)'}
            className="text-muted hover:text-text hover:bg-hover rounded-control mb-1.5 hidden h-8 shrink-0 cursor-pointer items-center gap-1.5 px-2.5 text-[12.5px] font-medium transition-colors lg:inline-flex"
          >
            {focused ? (
              <Minimize2 aria-hidden className="size-3.5" />
            ) : (
              <Maximize2 aria-hidden className="size-3.5" />
            )}
            {focused ? 'Show overview' : 'Expand editor'}
            <kbd className="border-line bg-surface text-faint ml-0.5 rounded border px-1 font-sans text-[10px] leading-[14px]">
              f
            </kbd>
          </button>
        </div>

        {/* The review takes a full screen below the tab bar; scroll down and it fills the window. */}
        <Tabs.Content
          value="review"
          className="tab-panel flex flex-col lg:h-[calc(100dvh-70px)] lg:min-h-[520px]"
        >
          <ReviewWorkspace
            scanId={scanId}
            files={files.data}
            visible={visible}
            total={all.length}
            hiddenCount={all.length - reported.length}
            loaded={findings.isSuccess}
            filter={filter}
            onFilter={setFilter}
          />
        </Tabs.Content>
        <Tabs.Content value="summary" className="tab-panel">
          <SummaryTab detail={detail} reported={reported} />
        </Tabs.Content>
        <Tabs.Content value="models" className="tab-panel">
          <ModelsTab calls={detail.calls} />
        </Tabs.Content>
      </Tabs.Root>
    </div>
  )
}

/**
 * Whether the page is scrolled so the tab bar sits at the top and the review fills the window,
 * and a toggle between that and the overview. `f` does the same from the keyboard.
 */
function useEditorFocus(sentinel: RefObject<HTMLDivElement | null>): [boolean, () => void] {
  const [focused, setFocused] = useState(false)

  useEffect(() => {
    const found = locate(sentinel.current)
    if (!found) return
    const onScroll = () => {
      const current = locate(sentinel.current)
      if (current) setFocused(current.main.scrollTop >= current.offset - 4)
    }
    found.main.addEventListener('scroll', onScroll, { passive: true })
    return () => found.main.removeEventListener('scroll', onScroll)
  }, [sentinel])

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== 'f' || event.metaKey || event.ctrlKey || event.altKey) return
      if (event.target instanceof HTMLElement && event.target.closest('input, select, textarea')) {
        return
      }
      toggleFocus(sentinel.current)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [sentinel])

  return [focused, () => toggleFocus(sentinel.current)]
}

/** The scrolling page and how far down it the tab bar sits before it sticks. */
function locate(marker: HTMLElement | null): { main: HTMLElement; offset: number } | null {
  const main = marker?.closest('main')
  if (!marker || !main) return null
  const offset =
    marker.getBoundingClientRect().top - main.getBoundingClientRect().top + main.scrollTop
  return { main, offset }
}

function toggleFocus(marker: HTMLElement | null): void {
  const found = locate(marker)
  if (!found) return
  const atReview = found.main.scrollTop >= found.offset - 4
  found.main.scrollTo({ top: atReview ? 0 : found.offset, behavior: 'smooth' })
}

function TabTrigger({
  value,
  icon: Icon,
  count,
  children,
}: {
  value: Tab
  icon: typeof Code2
  count?: number
  children: ReactNode
}) {
  return (
    <Tabs.Trigger
      value={value}
      className="group text-muted hover:text-text data-[state=active]:text-text focus-visible:bg-hover relative -mb-px flex h-10 cursor-pointer items-center gap-2 px-3 text-[13px] font-medium transition-colors outline-none focus-visible:rounded-t-md"
    >
      <Icon
        aria-hidden
        className="group-data-[state=active]:text-accent-text size-3.5 transition-colors"
      />
      {children}
      {count !== undefined && (
        <span className="bg-subtle group-data-[state=active]:bg-accent-soft group-data-[state=active]:text-accent-text rounded-full px-1.5 text-[11px] tabular-nums transition-colors">
          {count}
        </span>
      )}
      <span
        aria-hidden
        className="ease-out-expo absolute inset-x-2 bottom-0 h-[2px] origin-center scale-x-0 rounded-full bg-[linear-gradient(90deg,var(--color-accent),var(--color-accent-2))] transition-transform duration-300 group-data-[state=active]:scale-x-100"
      />
    </Tabs.Trigger>
  )
}
