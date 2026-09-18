import type { CallRecord } from '@/lib/api'
import { groupCalls } from '@/store/scan-store'

/** Which model received which file's code, and how each call went. */
export function ProvenanceTable({ calls }: { calls: CallRecord[] }) {
  const lanes = [...groupCalls(calls).entries()]
  if (lanes.length === 0) return null
  return (
    <details className="panel p-4">
      <summary className="cursor-pointer text-[15px] font-medium">
        Which model saw which file
      </summary>
      <table className="mt-2 w-full text-[13px]">
        <thead className="text-muted text-left">
          <tr>
            <th className="py-1">Provider</th>
            <th>Answered</th>
            <th>Other outcomes</th>
            <th>Files</th>
          </tr>
        </thead>
        <tbody>
          {lanes.map(([provider, records]) => {
            const answered = records.filter((call) => call.status === 'ok')
            const files = [
              ...new Set(
                records
                  .filter((call) => call.file_path && call.status !== 'skipped')
                  .map((call) => call.file_path as string),
              ),
            ]
            return (
              <tr key={provider} className="border-line/60 border-t align-top">
                <td className="py-1 font-medium">{provider}</td>
                <td className="tabular-nums">{answered.length}</td>
                <td className="text-muted">
                  {records.length - answered.length === 0
                    ? '—'
                    : [
                        ...new Set(records.filter((c) => c.status !== 'ok').map((c) => c.status)),
                      ].join(', ')}
                </td>
                <td className="path">{files.length > 0 ? files.join(', ') : '—'}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </details>
  )
}
