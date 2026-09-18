import type { CallRecord } from '@/lib/api'
import { groupCalls } from '@/store/scan-store'

const OK_STATUSES = ['ok', 'cached']

/** One lane per provider, showing how routing actually played out. */
export function ModelLanes({ calls }: { calls: CallRecord[] }) {
  const lanes = [...groupCalls(calls).entries()]
  if (lanes.length === 0) {
    return <p className="text-muted text-[13px]">No model calls yet.</p>
  }
  return (
    <ul className="space-y-2 text-[13px]">
      {lanes.map(([provider, records]) => {
        const answered = records.filter((call) => OK_STATUSES.includes(call.status))
        const problems = records.filter((call) => !OK_STATUSES.includes(call.status))
        const last = records[records.length - 1]
        return (
          <li key={provider} className="space-y-0.5">
            <div className="flex items-center gap-2">
              <span className="font-medium">{provider}</span>
              <span className="text-muted tabular-nums">
                {answered.length} answered
                {problems.length > 0 && `, ${problems.length} fell back`}
              </span>
            </div>
            <div className="text-muted flex flex-wrap gap-1">
              {records.slice(-12).map((call, index) => (
                <span
                  key={index}
                  title={`${call.task}: ${call.status}${call.detail ? ` — ${call.detail}` : ''}`}
                  className={`mark-in size-1.5 rounded-full ${
                    OK_STATUSES.includes(call.status) ? 'bg-low' : 'bg-medium'
                  }`}
                />
              ))}
              {last?.file_path && <span className="path truncate">{last.file_path}</span>}
            </div>
          </li>
        )
      })}
    </ul>
  )
}
