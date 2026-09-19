import { CircleCheck, CircleMinus, CircleX, LoaderCircle } from 'lucide-react'

import type { ToolEvent, ToolState } from '@/lib/events'

const STATE: Record<ToolState, { label: string; icon: typeof CircleCheck; className: string }> = {
  started: { label: 'Running', icon: LoaderCircle, className: 'text-accent-text' },
  ok: { label: 'Done', icon: CircleCheck, className: 'text-success' },
  failed: { label: 'Failed', icon: CircleX, className: 'text-critical' },
  skipped: { label: 'Skipped', icon: CircleMinus, className: 'text-faint' },
  timed_out: { label: 'Timed out', icon: CircleX, className: 'text-medium' },
}

/** Each analyzer with its outcome, finding count and time. */
export function ToolList({ tools }: { tools: ToolEvent[] }) {
  if (tools.length === 0)
    return <p className="text-muted shimmer px-4 py-4 text-[13px]">Waiting for analyzers…</p>
  return (
    <table className="w-full text-[13px]">
      <thead>
        <tr className="text-faint bg-subtle/40 text-left text-[11px] tracking-wide uppercase">
          <th className="px-4 py-2 font-medium">Analyzer</th>
          <th className="py-2 font-medium">Status</th>
          <th className="py-2 text-right font-medium">Findings</th>
          <th className="px-4 py-2 text-right font-medium">Time</th>
        </tr>
      </thead>
      <tbody className="divide-line divide-y border-t border-line">
        {[...tools]
          .sort((a, b) => a.tool.localeCompare(b.tool))
          .map((tool) => {
            const state = STATE[tool.state]
            const Icon = state.icon
            return (
              <tr key={tool.tool} className="fade-in hover:bg-subtle/60 transition-colors">
                <td className="mono px-4 py-2 text-[12.5px]">{tool.tool}</td>
                <td className="py-2">
                  <span className={`inline-flex items-center gap-1.5 ${state.className}`}>
                    <Icon
                      aria-hidden
                      className={`size-3.5 ${tool.state === 'started' ? 'animate-spin' : ''}`}
                    />
                    <span className="text-[12.5px]">{state.label}</span>
                  </span>
                </td>
                <td className="py-2 text-right tabular-nums">
                  {tool.state === 'started' ? '—' : tool.finding_count}
                </td>
                <td className="text-muted px-4 py-2 text-right tabular-nums">
                  {tool.state === 'started' ? '—' : `${(tool.duration_ms / 1000).toFixed(1)} s`}
                </td>
              </tr>
            )
          })}
      </tbody>
    </table>
  )
}
