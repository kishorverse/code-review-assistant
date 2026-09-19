import type { CallRecord } from '@/lib/api'
import { groupCalls } from '@/store/scan-store'

const ANSWERED = ['ok', 'cached']

/** One row per provider, showing how routing actually played out. */
export function ModelLanes({ calls }: { calls: CallRecord[] }) {
  const lanes = [...groupCalls(calls).entries()]
  if (lanes.length === 0) {
    return <p className="text-muted px-4 py-4 text-[13px]">No model calls yet.</p>
  }
  return (
    <table className="w-full text-[13px]">
      <thead>
        <tr className="text-faint bg-subtle/40 text-left text-[11px] tracking-wide uppercase">
          <th className="px-4 py-2 font-medium">Provider</th>
          <th className="py-2 font-medium">Recent calls</th>
          <th className="py-2 text-right font-medium">Answered</th>
          <th className="px-4 py-2 text-right font-medium">Passed on</th>
        </tr>
      </thead>
      <tbody className="divide-line border-line divide-y border-t">
        {lanes.map(([provider, records]) => {
          const answered = records.filter((call) => ANSWERED.includes(call.status))
          const attempted = records.filter((call) => call.status !== 'skipped')
          return (
            <tr key={provider} className="fade-in hover:bg-subtle/60 transition-colors">
              <td className="px-4 py-2">
                <span className="text-[13px] font-medium">{provider}</span>
                <span className="mono text-faint block max-w-44 truncate text-[11px]">
                  {records[0]?.model}
                </span>
              </td>
              <td className="py-2">
                <span className="flex flex-wrap gap-0.5">
                  {records.slice(-14).map((call, index) => (
                    <span
                      key={index}
                      title={`${call.task} · ${call.status}${call.detail ? ` · ${call.detail}` : ''}`}
                      className={`fade-in h-4 w-1.5 rounded-[2px] ${
                        ANSWERED.includes(call.status)
                          ? 'bg-success/80'
                          : call.status === 'skipped'
                            ? 'bg-line-strong'
                            : 'bg-medium/80'
                      }`}
                    />
                  ))}
                </span>
              </td>
              <td className="py-2 text-right tabular-nums">{answered.length}</td>
              <td className="text-muted px-4 py-2 text-right tabular-nums">
                {attempted.length - answered.length}
              </td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}
