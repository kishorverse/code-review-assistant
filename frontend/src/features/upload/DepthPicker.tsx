import type { Depth } from '@/lib/api'

const OPTIONS: {
  value: Depth
  label: string
  description: string
  cost: string
  level: number
}[] = [
  {
    value: 'static',
    label: 'Static only',
    description: 'Eight analyzers, no models. Nothing leaves this machine.',
    cost: 'Seconds',
    level: 1,
  },
  {
    value: 'quick',
    label: 'Quick',
    description: 'Models review the chunks analyzers flagged as risky.',
    cost: 'Fewest calls',
    level: 2,
  },
  {
    value: 'standard',
    label: 'Standard',
    description:
      'Every chunk for bugs, security, performance and style; serious AI findings cross-checked.',
    cost: 'Recommended',
    level: 3,
  },
  {
    value: 'deep',
    label: 'Deep',
    description: 'As standard, and a second model also checks medium-severity findings.',
    cost: 'Most calls',
    level: 4,
  },
]

/** How thoroughly models review. Each option says what it does and costs. */
export function DepthPicker({
  depth,
  onChange,
}: {
  depth: Depth
  onChange: (depth: Depth) => void
}) {
  return (
    <fieldset className="grid gap-2.5 sm:grid-cols-2">
      <legend className="sr-only">Review depth</legend>
      {OPTIONS.map((option) => {
        const checked = depth === option.value
        return (
          <label
            key={option.value}
            className={`group relative flex cursor-pointer flex-col gap-2 rounded-[12px] border px-4 py-3.5 transition-all duration-300 ease-out-expo has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-accent ${
              checked
                ? 'border-accent/50 bg-accent-soft/70 shadow-[0_0_0_3px_color-mix(in_srgb,var(--color-accent)_12%,transparent)]'
                : 'border-line bg-surface hover:border-line-strong hover:-translate-y-px hover:shadow-[0_4px_12px_-6px_rgb(0_0_0/0.12)]'
            }`}
          >
            <input
              type="radio"
              name="depth"
              value={option.value}
              checked={checked}
              onChange={() => onChange(option.value)}
              className="sr-only"
            />
            <span className="flex items-center gap-2.5">
              <span
                aria-hidden
                className={`grid size-4 shrink-0 place-items-center rounded-full border transition-colors duration-300 ${
                  checked ? 'border-accent bg-accent' : 'border-line-strong bg-surface'
                }`}
              >
                <span
                  className={`size-1.5 rounded-full bg-white transition-transform duration-300 ease-spring ${
                    checked ? 'scale-100' : 'scale-0'
                  }`}
                />
              </span>
              <span className="text-[13.5px] font-medium">{option.label}</span>
              <Meter level={option.level} active={checked} />
            </span>
            <span className="text-muted text-[12.5px] leading-relaxed">{option.description}</span>
            <span
              className={`mt-auto self-start rounded-full px-2 py-px text-[11px] font-medium transition-colors ${
                checked
                  ? 'bg-accent/12 text-accent-text'
                  : option.value === 'standard'
                    ? 'bg-subtle text-muted'
                    : 'text-faint bg-subtle'
              }`}
            >
              {option.cost}
            </span>
          </label>
        )
      })}
    </fieldset>
  )
}

/** Four bars: how much work this depth asks of the models. */
function Meter({ level, active }: { level: number; active: boolean }) {
  return (
    <span aria-hidden className="ml-auto flex items-end gap-[3px]">
      {[1, 2, 3, 4].map((bar) => (
        <span
          key={bar}
          style={{ height: 4 + bar * 3, transitionDelay: `${bar * 40}ms` }}
          className={`w-[3px] rounded-full transition-colors duration-300 ${
            bar <= level ? (active ? 'bg-accent' : 'bg-faint/60') : 'bg-line'
          }`}
        />
      ))}
    </span>
  )
}
