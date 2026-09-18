import type { Depth } from '@/lib/api'

const OPTIONS: { value: Depth; label: string; description: string }[] = [
  { value: 'static', label: 'Static only', description: 'Analyzers, no models' },
  { value: 'quick', label: 'Quick', description: 'Review risky chunks' },
  { value: 'standard', label: 'Standard', description: 'Review every chunk' },
  { value: 'deep', label: 'Deep', description: 'Cross-check more findings' },
]

/** How thoroughly models review. Each option says what it does. */
export function DepthPicker({
  depth,
  onChange,
}: {
  depth: Depth
  onChange: (depth: Depth) => void
}) {
  return (
    <fieldset>
      <legend className="mb-2 font-medium">Review depth</legend>
      <div className="grid gap-2 sm:grid-cols-4">
        {OPTIONS.map((option) => (
          <label
            key={option.value}
            className={`rounded-control cursor-pointer border p-3 text-[13px] ${
              depth === option.value
                ? 'border-brand bg-brand-soft'
                : 'border-line bg-panel hover:border-brand/60'
            }`}
          >
            <input
              type="radio"
              name="depth"
              value={option.value}
              checked={depth === option.value}
              onChange={() => onChange(option.value)}
              className="sr-only"
            />
            <span className="block font-medium text-[15px]">{option.label}</span>
            <span className="text-muted">{option.description}</span>
          </label>
        ))}
      </div>
    </fieldset>
  )
}
