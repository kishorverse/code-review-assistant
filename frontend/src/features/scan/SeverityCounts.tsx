import type { Finding } from '@/lib/api'
import { SEVERITIES, SEVERITY_DOT, SEVERITY_LABEL, countBySeverity } from '@/lib/severity'

/** Findings so far, by severity: a proportional bar with a labelled legend. */
export function SeverityCounts({ findings }: { findings: Finding[] }) {
  const counts = countBySeverity(findings)
  const total = findings.length
  return (
    <div className="space-y-2.5">
      <div className="bg-subtle flex h-2 gap-px overflow-hidden rounded-full" aria-hidden>
        {total > 0 &&
          SEVERITIES.map((severity) =>
            counts[severity] > 0 ? (
              <span
                key={severity}
                className={`${SEVERITY_DOT[severity]} transition-[width] duration-700 ease-out-expo first:rounded-l-full last:rounded-r-full`}
                style={{ width: `${(counts[severity] / total) * 100}%` }}
              />
            ) : null,
          )}
      </div>
      <ul className="flex flex-wrap gap-x-4 gap-y-1.5 text-[12.5px]">
        {SEVERITIES.map((severity) => (
          <li key={severity} className="flex items-center gap-1.5">
            <span aria-hidden className={`size-2 rounded-full ${SEVERITY_DOT[severity]}`} />
            <span className="text-muted">{SEVERITY_LABEL[severity]}</span>
            <span className="font-medium tabular-nums">{counts[severity]}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}
