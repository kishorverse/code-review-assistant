import { ChevronDown, X } from 'lucide-react'
import type { ReactNode } from 'react'

import type { Category, Severity } from '@/lib/api'
import type { FindingFilter, SourceKind } from '@/lib/filters'
import { SEVERITIES, SEVERITY_LABEL } from '@/lib/severity'

const CATEGORIES: Category[] = [
  'bug',
  'security',
  'performance',
  'maintainability',
  'style',
  'typing',
]

/** Severity, category, source and hidden-finding filters, as a compact toolbar. */
export function FindingFilters({
  filter,
  onChange,
  hiddenCount,
}: {
  filter: FindingFilter
  onChange: (filter: FindingFilter) => void
  hiddenCount: number
}) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Select
        label="Minimum severity"
        value={filter.minSeverity}
        onChange={(value) => onChange({ ...filter, minSeverity: value as Severity | 'any' })}
      >
        <option value="any">All severities</option>
        {SEVERITIES.map((severity) => (
          <option key={severity} value={severity}>
            {SEVERITY_LABEL[severity]} and above
          </option>
        ))}
      </Select>
      <Select
        label="Category"
        value={filter.category}
        onChange={(value) => onChange({ ...filter, category: value as Category | 'any' })}
      >
        <option value="any">All categories</option>
        {CATEGORIES.map((category) => (
          <option key={category} value={category}>
            {category[0]?.toUpperCase()}
            {category.slice(1)}
          </option>
        ))}
      </Select>
      <Select
        label="Found by"
        value={filter.source}
        onChange={(value) => onChange({ ...filter, source: value as SourceKind })}
      >
        <option value="any">Analyzers and models</option>
        <option value="tools">Analyzers</option>
        <option value="models">Models</option>
      </Select>
      {filter.file && (
        <button
          type="button"
          onClick={() => onChange({ ...filter, file: null })}
          className="fade-in rounded-control border-accent/30 bg-accent-soft text-accent-text hover:border-accent/60 inline-flex h-8 cursor-pointer items-center gap-1.5 border px-2.5 text-[12px] transition-colors"
        >
          <span className="mono max-w-48 truncate">{filter.file}</span>
          <X aria-hidden className="size-3" />
          <span className="sr-only">Clear the file filter</span>
        </button>
      )}
      <label className="text-muted ml-auto flex cursor-pointer items-center gap-2 text-[12.5px]">
        <input
          type="checkbox"
          className="accent-accent size-3.5"
          checked={filter.includeHidden}
          onChange={(event) => onChange({ ...filter, includeHidden: event.target.checked })}
        />
        Show dismissed and low-confidence ({hiddenCount})
      </label>
    </div>
  )
}

function Select({
  label,
  value,
  onChange,
  children,
}: {
  label: string
  value: string
  onChange: (value: string) => void
  children: ReactNode
}) {
  return (
    <label className="relative inline-flex">
      <span className="sr-only">{label}</span>
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="rounded-control border-line bg-surface hover:border-line-strong hover:bg-subtle h-8 cursor-pointer appearance-none border pr-8 pl-3 text-[12.5px] shadow-[0_1px_2px_rgb(0_0_0/0.04)] transition-colors"
      >
        {children}
      </select>
      <ChevronDown
        aria-hidden
        className="text-faint pointer-events-none absolute top-1/2 right-2 size-3.5 -translate-y-1/2"
      />
    </label>
  )
}
