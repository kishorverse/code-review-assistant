import type { ReactNode } from 'react'

import { stagger } from '@/lib/utils'

/** A bordered section with a small title row. `order` staggers its entrance. */
export function Panel({
  title,
  aside,
  className = '',
  order = 0,
  children,
}: {
  title: string
  aside?: ReactNode
  className?: string
  order?: number
  children: ReactNode
}) {
  return (
    <section className={`rise panel min-w-0 overflow-hidden ${className}`} style={stagger(order)}>
      <header className="border-line/70 flex h-11 items-center gap-2 border-b px-4">
        <h2 className="text-[13px] font-semibold tracking-tight">{title}</h2>
        {aside && (
          <span className="text-faint ml-auto truncate text-[12px] tabular-nums">{aside}</span>
        )}
      </header>
      {children}
    </section>
  )
}
