import type { Severity } from '@/lib/api'
import { SEVERITY_CLASS } from '@/lib/severity'

/** A severity label. The colour is decoration; the word carries the meaning. */
export function SeverityChip({ severity, count }: { severity: Severity; count?: number }) {
  return (
    <span
      className={`rounded-chip inline-flex items-center gap-1 border px-1.5 text-[13px] font-medium ${SEVERITY_CLASS[severity]}`}
    >
      {severity}
      {count !== undefined && <span className="tabular-nums">{count}</span>}
    </span>
  )
}
