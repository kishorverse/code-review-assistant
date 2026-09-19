import { ChevronDown, ListFilter, Search, X } from 'lucide-react'
import { Popover } from 'radix-ui'
import type { ReactNode } from 'react'

import type { Category, Severity } from '@/lib/api'
import { EMPTY_FILTER, activeFilterCount, type FindingFilter, type SourceKind } from '@/lib/filters'
import { SEVERITIES, SEVERITY_LABEL } from '@/lib/severity'

const CATEGORIES: Category[] = [
  'bug',
  'security',
  'performance',
  'maintainability',
  'style',
  'typing',
]

/** Search, plus severity, category, source and hidden-finding filters in a popover. */
export function FindingFilters({
  filter,
  onChange,
  hiddenCount,
}: {
  filter: FindingFilter
  onChange: (filter: FindingFilter) => void
  hiddenCount: number
}) {
  const active = activeFilterCount(filter)
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <label className="group relative min-w-0 flex-1">
          <span className="sr-only">Search findings</span>
          <Search
            aria-hidden
            className="text-faint group-focus-within:text-accent-text pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 transition-colors"
          />
          <input
            type="search"
            value={filter.query ?? ''}
            onChange={(event) => onChange({ ...filter, query: event.target.value })}
            placeholder="Search findings"
            className="rounded-control border-line bg-surface placeholder:text-faint hover:border-line-strong focus:border-accent/60 h-8 w-full border pr-2.5 pl-8 text-[12.5px] shadow-[0_1px_2px_rgb(0_0_0/0.04)] transition-colors outline-none focus:shadow-[0_0_0_3px_color-mix(in_srgb,var(--color-accent)_14%,transparent)]"
          />
        </label>
        <Popover.Root>
          <Popover.Trigger asChild>
            <button
              type="button"
              className={`rounded-control inline-flex h-8 shrink-0 cursor-pointer items-center gap-1.5 border px-2.5 text-[12.5px] font-medium shadow-[0_1px_2px_rgb(0_0_0/0.04)] transition-colors ${
                active > 0
                  ? 'border-accent/40 bg-accent-soft text-accent-text'
                  : 'border-line bg-surface text-muted hover:text-text hover:border-line-strong'
              }`}
            >
              <ListFilter aria-hidden className="size-3.5" />
              Filter
              {active > 0 && (
                <span className="bg-accent text-on-accent grid size-4 place-items-center rounded-full text-[10px] tabular-nums">
                  {active}
                </span>
              )}
            </button>
          </Popover.Trigger>
          <Popover.Portal>
            <Popover.Content
              align="end"
              sideOffset={6}
              className="border-line bg-elevated shadow-lift data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:zoom-in-95 data-[state=closed]:animate-out data-[state=closed]:fade-out-0 z-50 w-72 space-y-3 rounded-[12px] border p-3.5 text-[12.5px]"
            >
              <Field label="Minimum severity">
                <Select
                  label="Minimum severity"
                  value={filter.minSeverity}
                  onChange={(value) =>
                    onChange({ ...filter, minSeverity: value as Severity | 'any' })
                  }
                >
                  <option value="any">All severities</option>
                  {SEVERITIES.map((severity) => (
                    <option key={severity} value={severity}>
                      {SEVERITY_LABEL[severity]} and above
                    </option>
                  ))}
                </Select>
              </Field>
              <Field label="Category">
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
              </Field>
              <Field label="Found by">
                <Select
                  label="Found by"
                  value={filter.source}
                  onChange={(value) => onChange({ ...filter, source: value as SourceKind })}
                >
                  <option value="any">Analyzers and models</option>
                  <option value="tools">Analyzers</option>
                  <option value="models">Models</option>
                </Select>
              </Field>
              <label className="text-muted flex cursor-pointer items-center gap-2 pt-0.5">
                <input
                  type="checkbox"
                  className="accent-accent size-3.5"
                  checked={filter.includeHidden}
                  onChange={(event) => onChange({ ...filter, includeHidden: event.target.checked })}
                />
                Show dismissed and low-confidence ({hiddenCount})
              </label>
              <div className="border-line flex justify-end border-t pt-2.5">
                <button
                  type="button"
                  disabled={active === 0}
                  onClick={() =>
                    onChange({ ...EMPTY_FILTER, file: filter.file, query: filter.query })
                  }
                  className="text-accent-text cursor-pointer text-[12px] font-medium hover:underline disabled:cursor-default disabled:opacity-40 disabled:hover:no-underline"
                >
                  Reset filters
                </button>
              </div>
            </Popover.Content>
          </Popover.Portal>
        </Popover.Root>
      </div>
      {filter.file && (
        <button
          type="button"
          onClick={() => onChange({ ...filter, file: null })}
          className="fade-in rounded-control border-accent/30 bg-accent-soft text-accent-text hover:border-accent/60 inline-flex h-6 max-w-full cursor-pointer items-center gap-1.5 border px-2 text-[11.5px] transition-colors"
        >
          <span className="shrink-0 opacity-70">In</span>
          <span className="mono min-w-0 truncate">{filter.file}</span>
          <X aria-hidden className="size-3 shrink-0" />
          <span className="sr-only">Clear the file filter</span>
        </button>
      )}
    </div>
  )
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="space-y-1">
      <p className="eyebrow">{label}</p>
      {children}
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
    <label className="relative flex">
      <span className="sr-only">{label}</span>
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="rounded-control border-line bg-surface hover:border-line-strong h-8 w-full cursor-pointer appearance-none border pr-8 pl-2.5 text-[12.5px] transition-colors"
      >
        {children}
      </select>
      <ChevronDown
        aria-hidden
        className="text-faint pointer-events-none absolute top-1/2 right-2.5 size-3.5 -translate-y-1/2"
      />
    </label>
  )
}
