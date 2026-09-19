import { useQuery, useQueryClient } from '@tanstack/react-query'
import { CircleAlert, FileQuestion, Plus } from 'lucide-react'
import { useEffect, useMemo } from 'react'
import { Link, useParams } from 'react-router'

import { PageHeader } from '@/components/AppShell'
import { StatusBadge } from '@/components/StatusBadge'
import { Button } from '@/components/ui/button'
import { ReportLinks } from '@/features/results/ReportLinks'
import { ResultsView } from '@/features/results/ResultsView'
import { ScanProgress } from '@/features/scan/ScanProgress'
import { useScanEvents } from '@/hooks/use-scan-events'
import { ApiError, getScan, type ScanInfo } from '@/lib/api'
import { forgetScan, rememberScan } from '@/lib/recent'
import { compareFindings } from '@/lib/severity'
import { selectFindings, useScanStore } from '@/store/scan-store'

const DEPTH_LABEL: Record<string, string> = {
  static: 'Static only',
  quick: 'Quick review',
  standard: 'Standard review',
  deep: 'Deep review',
}

/** One page per scan: progress while it runs, then the results workspace. */
export function ScanPage() {
  const { scanId = '' } = useParams()
  const queryClient = useQueryClient()
  const store = useScanStore()
  const liveFindings = useMemo(() => selectFindings(store).sort(compareFindings), [store])

  useScanEvents(scanId, () => {
    void queryClient.invalidateQueries({ queryKey: ['scan', scanId] })
  })

  const scan = useQuery({
    queryKey: ['scan', scanId],
    queryFn: () => getScan(scanId),
    retry: (failures, error) => !isGone(error) && failures < 1,
    refetchInterval: (query) => {
      const status = query.state.data?.scan.status
      return status === 'done' || status === 'failed' || isGone(query.state.error) ? false : 4000
    },
  })

  const info = scan.data?.scan
  useEffect(() => {
    if (info) rememberScan({ id: info.id, source: info.source, createdAt: info.created_at })
  }, [info])
  useEffect(() => {
    if (isGone(scan.error)) forgetScan(scanId)
  }, [scan.error, scanId])

  if (isGone(scan.error)) {
    return (
      <div className="rise mx-auto max-w-lg px-6 py-28 text-center">
        <span className="border-line bg-surface shadow-panel mx-auto grid size-12 place-items-center rounded-2xl border">
          <FileQuestion aria-hidden className="text-faint size-5" />
        </span>
        <h1 className="display mt-6 text-[40px] leading-none">Scan not found</h1>
        <p className="text-muted mt-3 text-[13.5px] leading-relaxed">
          This scan does not exist, or it has been deleted: uploads and their results are kept for a
          limited time only.
        </p>
        <Link
          to="/"
          className="text-accent-text mt-5 inline-block text-[13.5px] font-medium hover:underline"
        >
          Start a new scan
        </Link>
      </div>
    )
  }

  const status = info?.status ?? store.status
  const failed = status === 'failed'
  const error = info?.error ?? store.message

  const done = status === 'done' && scan.data !== undefined

  return (
    <div>
      <PageHeader
        crumbs={[{ label: 'Reviews', to: '/' }, { label: info?.source ?? 'Scan' }]}
        title={info?.source ?? 'Scan'}
        badge={<StatusBadge status={status} />}
        meta={info && <Meta info={info} />}
        actions={
          <>
            {status === 'done' && <ReportLinks scanId={scanId} />}
            <Button asChild variant={status === 'done' ? 'ghost' : 'secondary'}>
              <Link to="/">
                <Plus aria-hidden />
                New review
              </Link>
            </Button>
          </>
        }
      />
      {done && scan.data ? (
        <div className="px-4 pt-4 pb-4 lg:px-6">
          <ResultsView scanId={scanId} detail={scan.data} />
        </div>
      ) : (
        <div className="mx-auto max-w-[1600px] px-6 py-6 lg:px-8">
          {failed ? (
            <div className="rise panel border-critical/30 flex items-start gap-3.5 px-5 py-4.5">
              <span className="bg-critical/10 text-critical grid size-8 shrink-0 place-items-center rounded-full">
                <CircleAlert aria-hidden className="size-4" />
              </span>
              <div>
                <p className="text-[13.5px] font-medium">The scan failed</p>
                <p className="text-muted mt-0.5 text-[13px]">
                  {error ?? 'Something went wrong. Please try again.'}
                </p>
              </div>
            </div>
          ) : (
            <ScanProgress
              stage={store.stage}
              finishedStages={store.finishedStages}
              tools={store.tools}
              calls={store.calls}
              plan={store.plan}
              findings={liveFindings}
              activity={store.activity}
            />
          )}
        </div>
      )}
    </div>
  )
}

function Meta({ info }: { info: ScanInfo }) {
  const started = info.started_at ?? info.created_at
  const seconds =
    info.finished_at && info.started_at
      ? Math.round((Date.parse(info.finished_at) - Date.parse(info.started_at)) / 1000)
      : null
  const parts = [
    DEPTH_LABEL[info.depth] ?? info.depth,
    info.allow_external ? 'hosted models allowed' : 'no hosted models',
    `started ${new Date(started).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })}`,
    seconds !== null
      ? `took ${seconds < 90 ? `${seconds} s` : `${Math.round(seconds / 60)} min`}`
      : null,
  ]
  return <>{parts.filter(Boolean).join(' · ')}</>
}

function isGone(error: unknown): boolean {
  return error instanceof ApiError && error.status === 404
}
