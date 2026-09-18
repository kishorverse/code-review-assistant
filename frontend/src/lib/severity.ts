/** Severity and status presentation. Colour is never the only signal: every
 * mark carries a label, and every card states its status in words.
 */
import type { Finding, FindingStatus, Severity } from '@/lib/api'

export const SEVERITIES: Severity[] = ['critical', 'high', 'medium', 'low', 'info']

const RANK: Record<Severity, number> = { critical: 4, high: 3, medium: 2, low: 1, info: 0 }

export const severityRank = (severity: Severity) => RANK[severity]

/** Tailwind classes per severity: text, border and a soft background. */
export const SEVERITY_CLASS: Record<Severity, string> = {
  critical: 'text-critical border-critical/40 bg-critical/10',
  high: 'text-high border-high/40 bg-high/10',
  medium: 'text-medium border-medium/40 bg-medium/10',
  low: 'text-low border-low/40 bg-low/10',
  info: 'text-info border-info/40 bg-info/10',
}

export const SEVERITY_DOT: Record<Severity, string> = {
  critical: 'bg-critical',
  high: 'bg-high',
  medium: 'bg-medium',
  low: 'bg-low',
  info: 'bg-info',
}

export const STATUS_LABEL: Record<FindingStatus, string> = {
  open: 'Open',
  needs_review: 'Needs human review',
  dismissed_by_ai: 'Dismissed by AI review',
  accepted: 'Accepted',
  rejected: 'Rejected',
}

export const AI_PROVIDERS = ['gemini', 'nvidia', 'hf-large', 'hf-small', 'local']

export const isAiOnly = (finding: Finding) =>
  finding.sources.every((source) => AI_PROVIDERS.includes(source))

export const hasModelSource = (finding: Finding) =>
  finding.sources.some((source) => AI_PROVIDERS.includes(source))

/** Sort order used everywhere: most severe first, then by location. */
export function compareFindings(a: Finding, b: Finding): number {
  return (
    severityRank(b.severity) - severityRank(a.severity) ||
    a.file_path.localeCompare(b.file_path) ||
    a.start_line - b.start_line
  )
}

export function countBySeverity(findings: Finding[]): Record<Severity, number> {
  const counts: Record<Severity, number> = { critical: 0, high: 0, medium: 0, low: 0, info: 0 }
  for (const finding of findings) counts[finding.severity] += 1
  return counts
}
