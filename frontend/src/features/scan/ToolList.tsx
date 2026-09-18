import type { ToolEvent } from '@/lib/events'

const STATE_LABEL: Record<string, string> = {
  started: 'running',
  ok: 'ok',
  failed: 'failed',
  skipped: 'skipped',
  timed_out: 'timed out',
}

/** Each analyzer with its outcome and finding count. */
export function ToolList({ tools }: { tools: ToolEvent[] }) {
  if (tools.length === 0) return <p className="text-muted text-[13px]">Waiting for analyzers…</p>
  return (
    <table className="w-full text-[13px]">
      <tbody>
        {[...tools]
          .sort((a, b) => a.tool.localeCompare(b.tool))
          .map((tool) => (
            <tr key={tool.tool} className="border-line/60 border-b last:border-0">
              <td className="py-1 font-medium">{tool.tool}</td>
              <td className={tool.state === 'ok' ? 'text-muted' : 'text-medium'}>
                {STATE_LABEL[tool.state] ?? tool.state}
              </td>
              <td className="text-muted py-1 text-right tabular-nums">
                {tool.state === 'started' ? '…' : `${tool.finding_count} · ${tool.duration_ms} ms`}
              </td>
            </tr>
          ))}
      </tbody>
    </table>
  )
}
