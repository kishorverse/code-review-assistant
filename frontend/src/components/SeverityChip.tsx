import type { Severity } from '@/lib/api'
import { SEVERITY_CLASS, SEVERITY_DOT, SEVERITY_LABEL } from '@/lib/severity'

/** A severity badge. The colour is decoration; the word carries the meaning. */
export function SeverityChip({ severity, count }: { severity: Severity; count?: number }) {
  return (
    <span
      className={`inline-flex h-5 items-center gap-1.5 rounded-full border px-2 text-[11.5px] font-medium ${SEVERITY_CLASS[severity]}`}
    >
      <span aria-hidden className={`size-1.5 rounded-full ${SEVERITY_DOT[severity]}`} />
      {SEVERITY_LABEL[severity]}
      {count !== undefined && <span className="tabular-nums opacity-80">{count}</span>}
    </span>
  )
}
