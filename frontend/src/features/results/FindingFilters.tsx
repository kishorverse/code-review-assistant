import type { Category, Severity } from '@/lib/api'
import type { FindingFilter, SourceKind } from '@/lib/filters'
import { SEVERITIES } from '@/lib/severity'

const CATEGORIES: Category[] = [
  'bug',
  'security',
  'performance',
  'maintainability',
  'style',
  'typing',
]

/** Severity, category, source and hidden-finding filters. */
export function FindingFilters({
  filter,
  onChange,
  hiddenCount,
}: {
  filter: FindingFilter
  onChange: (filter: FindingFilter) => void
  hiddenCount: number
}) {
  const select = 'rounded-control border-line bg-panel px-2 py-1 text-[13px]'
  return (
    <div className="flex flex-wrap items-center gap-2">
      <label className="text-muted text-[13px]">
        <span className="sr-only">Minimum severity</span>
        <select
          className={select}
          value={filter.minSeverity}
          onChange={(event) =>
            onChange({ ...filter, minSeverity: event.target.value as Severity | 'any' })
          }
        >
          <option value="any">Any severity</option>
          {SEVERITIES.map((severity) => (
            <option key={severity} value={severity}>
              {severity} and above
            </option>
          ))}
        </select>
      </label>

      <label className="text-muted text-[13px]">
        <span className="sr-only">Category</span>
        <select
          className={select}
          value={filter.category}
          onChange={(event) =>
            onChange({ ...filter, category: event.target.value as Category | 'any' })
          }
        >
          <option value="any">Any category</option>
          {CATEGORIES.map((category) => (
            <option key={category} value={category}>
              {category}
            </option>
          ))}
        </select>
      </label>

      <label className="text-muted text-[13px]">
        <span className="sr-only">Found by</span>
        <select
          className={select}
          value={filter.source}
          onChange={(event) => onChange({ ...filter, source: event.target.value as SourceKind })}
        >
          <option value="any">Any source</option>
          <option value="tools">Analyzers</option>
          <option value="models">Models</option>
        </select>
      </label>

      {filter.file && (
        <button
          type="button"
          className="rounded-control border-line hover:border-brand border px-2 py-1 text-[13px]"
          onClick={() => onChange({ ...filter, file: null })}
        >
          <span className="path">{filter.file}</span> &times;
        </button>
      )}

      <label className="text-muted ml-auto flex items-center gap-1.5 text-[13px]">
        <input
          type="checkbox"
          className="accent-brand"
          checked={filter.includeHidden}
          onChange={(event) => onChange({ ...filter, includeHidden: event.target.checked })}
        />
        Show {hiddenCount} dismissed or low confidence
      </label>
    </div>
  )
}
