import { CircleAlert, CircleCheck, Clock } from 'lucide-react'

import type { ScanStatus } from '@/lib/api'

const STYLE: Record<ScanStatus, { label: string; className: string; icon: typeof Clock | null }> = {
  queued: { label: 'Queued', className: 'text-muted border-line bg-subtle', icon: Clock },
  running: {
    label: 'Running',
    className: 'text-accent-text border-accent/30 bg-accent-soft',
    icon: null,
  },
  done: {
    label: 'Completed',
    className: 'text-success border-success/25 bg-success/8',
    icon: CircleCheck,
  },
  failed: {
    label: 'Failed',
    className: 'text-critical border-critical/25 bg-critical/8',
    icon: CircleAlert,
  },
}

/** Where a review stands, in words and with an icon. */
export function StatusBadge({ status }: { status: ScanStatus | null }) {
  const style = STYLE[status ?? 'queued']
  const Icon = style.icon
  return (
    <span
      key={status ?? 'queued'}
      className={`fade-in inline-flex h-6 items-center gap-1.5 rounded-full border px-2.5 text-[12px] font-medium ${style.className}`}
    >
      {Icon ? (
        <Icon aria-hidden className="size-3.5" />
      ) : (
        <span aria-hidden className="relative flex size-2">
          <span className="bg-accent absolute inset-0 animate-ping rounded-full opacity-60" />
          <span className="bg-accent relative size-2 rounded-full" />
        </span>
      )}
      {style.label}
    </span>
  )
}
