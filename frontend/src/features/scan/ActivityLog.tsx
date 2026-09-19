import { useEffect, useRef } from 'react'

import type { ActivityLine, Tone } from '@/lib/activity'

const TONE: Record<Tone, string> = {
  info: 'text-muted',
  ok: 'text-text',
  warn: 'text-medium',
  error: 'text-critical',
}

function clock(at: number): string {
  return new Date(at).toLocaleTimeString(undefined, { hour12: false })
}

/** The scan's events as they happen, newest at the bottom. */
export function ActivityLog({ lines }: { lines: ActivityLine[] }) {
  const end = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const box = end.current?.parentElement
    if (box) box.scrollTop = box.scrollHeight
  }, [lines.length])

  return (
    <div
      role="log"
      aria-label="Scan activity"
      className="mono h-72 overflow-y-auto bg-[color-mix(in_srgb,var(--color-canvas)_70%,var(--color-surface))] px-4 py-3 text-[12px] leading-[1.75] motion-safe:scroll-smooth"
    >
      {lines.length === 0 ? (
        <p className="text-faint flex items-center gap-2">
          <span className="bg-accent inline-block h-3.5 w-1.5 animate-pulse rounded-[1px]" />
          Waiting for the first event…
        </p>
      ) : (
        lines.map((line, index) => (
          <div key={index} className="fade-in hover:bg-hover/60 -mx-2 flex gap-3 rounded px-2">
            <span className="text-faint shrink-0 tabular-nums">{clock(line.at)}</span>
            <span className="text-accent-text w-24 shrink-0 truncate">{line.source}</span>
            <span className={`min-w-0 ${TONE[line.tone]}`}>{line.text}</span>
          </div>
        ))
      )}
      <div ref={end} />
    </div>
  )
}
