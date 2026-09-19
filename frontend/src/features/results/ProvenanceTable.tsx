import { Panel } from '@/components/Panel'
import type { CallRecord } from '@/lib/api'
import { groupCalls } from '@/store/scan-store'

const ANSWERED = ['ok', 'cached']

/** Which model received which file's code, and how each call went. */
export function ProvenanceTable({ calls }: { calls: CallRecord[] }) {
  const lanes = [...groupCalls(calls).entries()]
  if (lanes.length === 0) return null
  return (
    <Panel title="Model provenance" aside="Which model saw which file" order={4}>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[720px] text-[13px]">
          <thead>
            <tr className="text-faint bg-subtle/40 text-left text-[11px] tracking-wide uppercase">
              <th className="px-4 py-2 font-medium">Provider</th>
              <th className="py-2 pr-4 text-right font-medium">Answered</th>
              <th className="py-2 pr-4 font-medium">Other outcomes</th>
              <th className="py-2 pr-4 text-right font-medium">Tokens in / out</th>
              <th className="py-2 pr-4 text-right font-medium">Median latency</th>
              <th className="py-2 pr-4 font-medium">Files</th>
            </tr>
          </thead>
          <tbody className="divide-line border-line divide-y border-t">
            {lanes.map(([provider, records]) => {
              const sent = records.filter((call) => call.status !== 'skipped')
              const answered = records.filter((call) => ANSWERED.includes(call.status))
              const others = countBy(
                records.filter((call) => !ANSWERED.includes(call.status)),
                (call) => call.status.replaceAll('_', ' '),
              )
              const files = [
                ...new Set(
                  sent.filter((call) => call.file_path).map((call) => call.file_path as string),
                ),
              ]
              return (
                <tr key={provider} className="hover:bg-subtle/60 align-top transition-colors">
                  <td className="px-4 py-2.5">
                    <span className="font-medium">{provider}</span>
                    <span className="mono text-faint block max-w-56 truncate text-[11px]">
                      {records[0]?.model}
                    </span>
                  </td>
                  <td className="py-2.5 pr-4 text-right tabular-nums">{answered.length}</td>
                  <td className="text-muted py-2.5 pr-4">
                    {others.length === 0
                      ? '—'
                      : others.map(([label, count]) => `${count} ${label}`).join(', ')}
                  </td>
                  <td className="text-muted py-2.5 pr-4 text-right tabular-nums">
                    {sum(answered, 'input_tokens').toLocaleString()} /{' '}
                    {sum(answered, 'output_tokens').toLocaleString()}
                  </td>
                  <td className="text-muted py-2.5 pr-4 text-right tabular-nums">
                    {answered.length > 0 ? `${(median(answered) / 1000).toFixed(1)} s` : '—'}
                  </td>
                  <td className="py-2.5 pr-4">
                    {files.length === 0 ? (
                      <span className="text-faint">—</span>
                    ) : (
                      <span className="mono text-muted block max-w-md text-[11.5px] leading-5">
                        {files.join(', ')}
                      </span>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </Panel>
  )
}

function countBy<T>(items: T[], key: (item: T) => string): [string, number][] {
  const counts = new Map<string, number>()
  for (const item of items) counts.set(key(item), (counts.get(key(item)) ?? 0) + 1)
  return [...counts.entries()]
}

function sum(calls: CallRecord[], field: 'input_tokens' | 'output_tokens'): number {
  return calls.reduce((total, call) => total + call[field], 0)
}

function median(calls: CallRecord[]): number {
  const sorted = calls.map((call) => call.latency_ms).sort((a, b) => a - b)
  const middle = Math.floor(sorted.length / 2)
  return sorted.length % 2
    ? (sorted[middle] ?? 0)
    : ((sorted[middle - 1] ?? 0) + (sorted[middle] ?? 0)) / 2
}
