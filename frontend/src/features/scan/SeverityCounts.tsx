import { SeverityChip } from '@/components/SeverityChip'
import type { Finding } from '@/lib/api'
import { SEVERITIES, countBySeverity } from '@/lib/severity'

/** Live severity totals. */
export function SeverityCounts({ findings }: { findings: Finding[] }) {
  const counts = countBySeverity(findings)
  const present = SEVERITIES.filter((severity) => counts[severity] > 0)
  return (
    <div className="flex flex-wrap items-center gap-2">
      {present.length === 0 ? (
        <span className="text-muted text-[13px]">Nothing found yet.</span>
      ) : (
        present.map((severity) => (
          <SeverityChip key={severity} severity={severity} count={counts[severity]} />
        ))
      )}
    </div>
  )
}
