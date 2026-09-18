/** Filtering of findings in the results view. */
import type { Category, Finding, Severity } from '@/lib/api'
import { hasModelSource, isAiOnly, severityRank } from '@/lib/severity'

export type SourceKind = 'any' | 'tools' | 'models'

export interface FindingFilter {
  minSeverity: Severity | 'any'
  category: Category | 'any'
  source: SourceKind
  file: string | null
  /** Include findings dismissed by AI review, rejected, or below the confidence threshold. */
  includeHidden: boolean
}

export const EMPTY_FILTER: FindingFilter = {
  minSeverity: 'any',
  category: 'any',
  source: 'any',
  file: null,
  includeHidden: false,
}

const HIDDEN_STATUSES = ['dismissed_by_ai', 'rejected']

/** Whether a finding is part of the default report. */
export function isReported(finding: Finding, minConfidence: number): boolean {
  if (HIDDEN_STATUSES.includes(finding.status)) return false
  return !isAiOnly(finding) || finding.confidence >= minConfidence
}

export function applyFilter(
  findings: Finding[],
  filter: FindingFilter,
  minConfidence: number,
): Finding[] {
  return findings.filter((finding) => {
    if (!filter.includeHidden && !isReported(finding, minConfidence)) return false
    if (
      filter.minSeverity !== 'any' &&
      severityRank(finding.severity) < severityRank(filter.minSeverity)
    ) {
      return false
    }
    if (filter.category !== 'any' && finding.category !== filter.category) return false
    if (filter.file && finding.file_path !== filter.file) return false
    if (filter.source === 'tools' && isAiOnly(finding)) return false
    if (filter.source === 'models' && !hasModelSource(finding)) return false
    return true
  })
}
