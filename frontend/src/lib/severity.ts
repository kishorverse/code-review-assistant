/** Severity and status presentation. Colour is never the only signal: every
 * mark carries a label, and every finding states its status in words.
 */
import type { Finding, FindingStatus, Severity } from '@/lib/api'

export const SEVERITIES: Severity[] = ['critical', 'high', 'medium', 'low', 'info']

const RANK: Record<Severity, number> = { critical: 4, high: 3, medium: 2, low: 1, info: 0 }

export const severityRank = (severity: Severity) => RANK[severity]

export const SEVERITY_LABEL: Record<Severity, string> = {
  critical: 'Critical',
  high: 'High',
  medium: 'Medium',
  low: 'Low',
  info: 'Info',
}

/** Text, border and tinted background for a severity badge. */
export const SEVERITY_CLASS: Record<Severity, string> = {
  critical: 'text-critical border-critical/25 bg-critical/8',
  high: 'text-high border-high/25 bg-high/8',
  medium: 'text-medium border-medium/30 bg-medium/10',
  low: 'text-low border-low/25 bg-low/8',
  info: 'text-info border-info/25 bg-info/8',
}

export const SEVERITY_DOT: Record<Severity, string> = {
  critical: 'bg-critical',
  high: 'bg-high',
  medium: 'bg-medium',
  low: 'bg-low',
  info: 'bg-info',
}

/** A severity's colour as a left edge, for annotations. */
export const SEVERITY_EDGE: Record<Severity, string> = {
  critical: 'border-l-critical',
  high: 'border-l-high',
  medium: 'border-l-medium',
  low: 'border-l-low',
  info: 'border-l-info',
}

export const STATUS_LABEL: Record<FindingStatus, string> = {
  open: 'Open',
  needs_review: 'Needs review',
  dismissed_by_ai: 'Dismissed by AI',
  accepted: 'Accepted',
  rejected: 'Rejected',
}

export const AI_PROVIDERS = ['gemini', 'nvidia', 'hf-large', 'hf-small', 'local', 'mock']

export const isAiOnly = (finding: Finding) =>
  finding.sources.every((source) => AI_PROVIDERS.includes(source))

export const hasModelSource = (finding: Finding) =>
  finding.sources.some((source) => AI_PROVIDERS.includes(source))

export const isModel = (source: string) => AI_PROVIDERS.includes(source)

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
