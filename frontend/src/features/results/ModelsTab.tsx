import { Cpu } from 'lucide-react'

import { Panel } from '@/components/Panel'
import { ProvenanceTable } from '@/features/results/ProvenanceTable'
import type { CallRecord } from '@/lib/api'
import { stagger } from '@/lib/utils'

const ANSWERED = ['ok', 'cached']

const STATUS: Record<CallRecord['status'], { label: string; className: string }> = {
  ok: { label: 'Answered', className: 'text-success border-success/25 bg-success/8' },
  cached: { label: 'Cached', className: 'text-accent-text border-accent/25 bg-accent-soft' },
  rate_limited: { label: 'Rate limited', className: 'text-medium border-medium/30 bg-medium/10' },
  quota_exhausted: {
    label: 'Quota used up',
    className: 'text-medium border-medium/30 bg-medium/10',
  },
  auth_failed: {
    label: 'Auth failed',
    className: 'text-critical border-critical/25 bg-critical/8',
  },
  misconfigured: {
    label: 'Misconfigured',
    className: 'text-critical border-critical/25 bg-critical/8',
  },
  unavailable: { label: 'Unavailable', className: 'text-high border-high/25 bg-high/8' },
  rejected: { label: 'Rejected', className: 'text-high border-high/25 bg-high/8' },
  skipped: { label: 'Skipped', className: 'text-muted border-line bg-subtle' },
}

const TASK: Record<CallRecord['task'], string> = {
  review: 'Review',
  style: 'Style',
  verify: 'Cross-check',
  summarize: 'Summary',
}

/** How the models were used: totals, who saw which file, and every call in order. */
export function ModelsTab({ calls }: { calls: CallRecord[] }) {
  if (calls.length === 0) {
    return (
      <section className="rise panel flex flex-col items-center gap-3 px-5 py-12 text-center">
        <span className="border-line bg-subtle text-faint grid size-10 place-items-center rounded-xl border">
          <Cpu aria-hidden className="size-4.5" />
        </span>
        <p className="text-muted max-w-sm text-[13px] leading-relaxed">
          No model was called in this review: it ran the static analyzers only.
        </p>
      </section>
    )
  }

  const answered = calls.filter((call) => ANSWERED.includes(call.status))
  const tokensIn = answered.reduce((sum, call) => sum + call.input_tokens, 0)
  const tokensOut = answered.reduce((sum, call) => sum + call.output_tokens, 0)
  const providers = new Set(answered.map((call) => call.provider))
  const latencies = answered.map((call) => call.latency_ms).sort((a, b) => a - b)
  const median = latencies[Math.floor(latencies.length / 2)] ?? 0

  return (
    <div className="space-y-4 pb-2">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        <Stat label="Calls" value={calls.length} order={0} />
        <Stat label="Answered" value={answered.length} order={1} />
        <Stat
          label="Fell through"
          value={calls.length - answered.length}
          order={2}
          hint="Moved on to the next provider"
        />
        <Stat label="Providers used" value={providers.size} order={3} />
        <Stat
          label="Tokens in / out"
          value={`${compact(tokensIn)} / ${compact(tokensOut)}`}
          order={4}
          hint={`Median answer ${(median / 1000).toFixed(1)} s`}
        />
      </div>

      <ProvenanceTable calls={calls} />

      <Panel title="Call log" aside="Every model call, in order" order={5}>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[820px] text-[12.5px]">
            <thead>
              <tr className="text-faint bg-subtle/40 text-left text-[11px] tracking-wide uppercase">
                <th className="w-10 px-4 py-2 font-medium">#</th>
                <th className="py-2 pr-4 font-medium">Task</th>
                <th className="py-2 pr-4 font-medium">Provider</th>
                <th className="py-2 pr-4 font-medium">Outcome</th>
                <th className="py-2 pr-4 text-right font-medium">Time</th>
                <th className="py-2 pr-4 text-right font-medium">Tokens</th>
                <th className="py-2 pr-4 font-medium">File</th>
                <th className="py-2 pr-4 font-medium">Detail</th>
              </tr>
            </thead>
            <tbody className="divide-line border-line divide-y border-t">
              {calls.map((call, index) => {
                const status = STATUS[call.status]
                return (
                  <tr key={index} className="hover:bg-subtle/60 align-top transition-colors">
                    <td className="text-faint px-4 py-2 tabular-nums">{index + 1}</td>
                    <td className="py-2 pr-4">{TASK[call.task] ?? call.task}</td>
                    <td className="py-2 pr-4">
                      <span className="font-medium">{call.provider}</span>
                      <span className="mono text-faint block max-w-52 truncate text-[11px]">
                        {call.model}
                      </span>
                    </td>
                    <td className="py-2 pr-4">
                      <span
                        className={`inline-flex rounded-full border px-2 text-[11px] leading-[18px] font-medium whitespace-nowrap ${status.className}`}
                      >
                        {status.label}
                      </span>
                    </td>
                    <td className="text-muted py-2 pr-4 text-right tabular-nums">
                      {(call.latency_ms / 1000).toFixed(1)} s
                    </td>
                    <td className="text-muted py-2 pr-4 text-right tabular-nums">
                      {ANSWERED.includes(call.status)
                        ? `${call.input_tokens.toLocaleString()} / ${call.output_tokens.toLocaleString()}`
                        : '—'}
                    </td>
                    <td className="mono text-muted max-w-48 truncate py-2 pr-4 text-[11.5px]">
                      {call.file_path ?? '—'}
                    </td>
                    <td className="text-muted max-w-80 py-2 pr-4 text-[12px]">
                      <span className="line-clamp-2" title={call.detail ?? undefined}>
                        {call.detail ?? '—'}
                      </span>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </Panel>
    </div>
  )
}

function Stat({
  label,
  value,
  order,
  hint,
}: {
  label: string
  value: string | number
  order: number
  hint?: string
}) {
  return (
    <div className="rise panel px-4 py-3" style={stagger(order)}>
      <p className="eyebrow">{label}</p>
      <p className="mt-1 text-[20px] leading-tight font-semibold tracking-tight tabular-nums">
        {value}
      </p>
      {hint && <p className="text-faint mt-0.5 truncate text-[11.5px]">{hint}</p>}
    </div>
  )
}

function compact(value: number): string {
  return value >= 1000 ? `${(value / 1000).toFixed(1)}k` : String(value)
}
