import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useMemo } from 'react'
import { Link, useParams } from 'react-router'

import { ResultsView } from '@/features/results/ResultsView'
import { ScanProgress } from '@/features/scan/ScanProgress'
import { useScanEvents } from '@/hooks/use-scan-events'
import { ApiError, getScan } from '@/lib/api'
import { compareFindings } from '@/lib/severity'
import { selectFindings, useScanStore } from '@/store/scan-store'

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

  if (isGone(scan.error)) {
    return (
      <div className="mx-auto max-w-3xl space-y-3 px-4 py-10">
        <h1 className="text-[24px]">Scan not found</h1>
        <p className="text-muted">
          This scan does not exist, or it has been deleted: uploads and their results are kept for a
          limited time only.
        </p>
        <Link to="/" className="text-brand underline">
          Start a new scan
        </Link>
      </div>
    )
  }

  const status = scan.data?.scan.status ?? store.status
  const failed = status === 'failed'

  return (
    <div className="mx-auto max-w-[110rem] space-y-4 px-4 py-6">
      <header className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h1 className="text-[24px]">{scan.data ? scan.data.scan.source : 'Scan'}</h1>
        <p className="text-muted text-[13px]">
          {status === 'done'
            ? 'Review finished'
            : failed
              ? (scan.data?.scan.error ?? store.message ?? 'The scan failed.')
              : status === 'running'
                ? 'Scanning…'
                : 'Queued'}
        </p>
        <Link to="/" className="text-brand ml-auto text-[13px] underline">
          Scan another project
        </Link>
      </header>

      {status === 'done' && scan.data ? (
        <ResultsView scanId={scanId} detail={scan.data} />
      ) : failed ? (
        <p className="panel p-4">
          {scan.data?.scan.error ?? store.message ?? 'The scan failed. Please try again.'}
        </p>
      ) : (
        <ScanProgress
          stage={store.stage}
          finishedStages={store.finishedStages}
          tools={store.tools}
          calls={store.calls}
          plan={store.plan}
          findings={liveFindings}
        />
      )}
    </div>
  )
}

function isGone(error: unknown): boolean {
  return error instanceof ApiError && error.status === 404
}
