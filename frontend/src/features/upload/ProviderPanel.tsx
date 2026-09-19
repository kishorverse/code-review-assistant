import { Cloud, Laptop, ShieldCheck } from 'lucide-react'

import type { ProvidersView } from '@/lib/api'
import { stagger } from '@/lib/utils'

/** The configured models, and the consent gate for the hosted ones. */
export function ProviderPanel({
  providers,
  allowExternal,
  onAllowExternal,
  disabled,
}: {
  providers: ProvidersView | undefined
  allowExternal: boolean
  onAllowExternal: (allow: boolean) => void
  disabled: boolean
}) {
  const hosted = providers?.providers.filter((provider) => provider.external) ?? []
  const local = providers?.providers.filter((provider) => !provider.external) ?? []
  const on = allowExternal && !disabled

  return (
    <div className="space-y-3">
      {providers === undefined ? (
        <div className="space-y-2" aria-label="Checking which models are configured">
          {[0, 1, 2].map((row) => (
            <div key={row} className="shimmer bg-subtle h-11 rounded-[10px]" />
          ))}
        </div>
      ) : providers.providers.length === 0 ? (
        <p className="border-line text-muted rounded-[12px] border border-dashed px-4 py-3.5 text-[13px]">
          No models are configured, so static analysis runs alone. Add API keys or a local model in{' '}
          <code className="text-text">backend/.env</code> to enable AI review.
        </p>
      ) : (
        <ul className="border-line bg-surface divide-line divide-y overflow-hidden rounded-[12px] border">
          {providers.providers.map((provider, index) => {
            const Icon = provider.external ? Cloud : Laptop
            const paused = provider.state !== 'closed'
            return (
              <li
                key={provider.name}
                className="rise hover:bg-subtle/60 flex items-center gap-3 px-4 py-2.5 transition-colors"
                style={stagger(index)}
              >
                <span className="border-line bg-subtle text-muted grid size-7 shrink-0 place-items-center rounded-lg border">
                  <Icon aria-hidden className="size-3.5" />
                </span>
                <span className="w-20 shrink-0 text-[13px] font-medium whitespace-nowrap">
                  {provider.name}
                </span>
                <code className="text-muted min-w-0 flex-1 truncate text-[12px]">
                  {provider.model}
                </code>
                <span
                  className={`inline-flex shrink-0 items-center gap-1.5 rounded-full px-2 py-0.5 text-[11.5px] ${
                    paused ? 'text-medium bg-medium/10' : 'text-muted bg-subtle'
                  }`}
                >
                  <span className="relative flex size-1.5" aria-hidden>
                    {!paused && (
                      <span className="bg-success absolute inset-0 animate-ping rounded-full opacity-50 [animation-duration:2.4s]" />
                    )}
                    <span
                      className={`relative size-1.5 rounded-full ${paused ? 'bg-medium' : 'bg-success'}`}
                    />
                  </span>
                  {paused
                    ? `Paused: ${provider.reason ?? provider.state}`
                    : provider.external
                      ? 'Hosted'
                      : 'On this machine'}
                </span>
              </li>
            )
          })}
        </ul>
      )}
      {providers?.mode === 'mock' && (
        <p className="text-muted text-[12.5px]">
          Mock mode: answers are canned and nothing leaves the machine.
        </p>
      )}
      {hosted.length > 0 && (
        <label
          className={`flex items-start gap-3.5 rounded-[12px] border px-4 py-3.5 transition-all duration-300 has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-accent ${
            on
              ? 'border-accent/45 bg-accent-soft/70 shadow-[0_0_0_3px_color-mix(in_srgb,var(--color-accent)_10%,transparent)]'
              : 'border-line bg-surface'
          } ${disabled ? 'opacity-55' : 'hover:border-line-strong cursor-pointer'}`}
        >
          <input
            type="checkbox"
            checked={allowExternal}
            disabled={disabled}
            onChange={(event) => onAllowExternal(event.target.checked)}
            className="peer sr-only"
          />
          <span
            aria-hidden
            className={`relative mt-0.5 inline-flex h-5 w-9 shrink-0 rounded-full transition-colors duration-300 ${
              on ? 'bg-accent' : 'bg-line-strong'
            }`}
          >
            <span
              className={`absolute top-0.5 size-4 rounded-full bg-white shadow-[0_1px_3px_rgb(0_0_0/0.25)] transition-[left] duration-500 ease-spring ${
                on ? 'left-[18px]' : 'left-0.5'
              }`}
            />
          </span>
          <span className="min-w-0 flex-1">
            <span className="block text-[13.5px] font-medium">
              Send code excerpts to the hosted models ({hosted.map((p) => p.name).join(', ')}).
            </span>
            <span className="text-muted mt-1 block text-[12.5px] leading-relaxed">
              Detected secrets are masked first, and the report lists which model saw which file.
              {local.length > 0
                ? ' Without this, only the local model reviews your code.'
                : ' Without this, only static analysis runs.'}
            </span>
          </span>
          <ShieldCheck
            aria-hidden
            className={`mt-0.5 size-4 shrink-0 transition-colors duration-300 ${on ? 'text-accent-text' : 'text-faint'}`}
          />
        </label>
      )}
    </div>
  )
}
