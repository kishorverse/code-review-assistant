import type { ProvidersView } from '@/lib/api'

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

  return (
    <section className="panel space-y-3 p-4">
      <h2 className="text-[18px]">Models</h2>
      {providers === undefined ? (
        <p className="text-muted text-[13px]">Checking which models are configured…</p>
      ) : providers.providers.length === 0 ? (
        <p className="text-muted text-[13px]">
          No models are configured. Static analysis still runs; add API keys or a local model in
          <code className="path"> backend/.env</code> to enable AI review.
        </p>
      ) : (
        <ul className="space-y-1 text-[13px]">
          {providers.providers.map((provider) => (
            <li key={provider.name} className="flex items-center gap-2">
              <span
                aria-hidden
                className={`size-1.5 rounded-full ${
                  provider.state === 'closed' ? 'bg-low' : 'bg-medium'
                }`}
              />
              <span className="font-medium whitespace-nowrap">{provider.name}</span>
              <code className="path text-muted truncate">{provider.model}</code>
              <span className="text-muted ml-auto">
                {provider.external ? 'hosted' : 'on this machine'}
                {provider.state !== 'closed' && ` · paused: ${provider.reason ?? provider.state}`}
              </span>
            </li>
          ))}
          {providers.mode === 'mock' && (
            <li className="text-muted">
              Mock mode: answers are canned, nothing leaves the machine.
            </li>
          )}
        </ul>
      )}
      {hosted.length > 0 && (
        <label className="flex items-start gap-2 text-[13px]">
          <input
            type="checkbox"
            checked={allowExternal}
            disabled={disabled}
            onChange={(event) => onAllowExternal(event.target.checked)}
            className="accent-brand mt-1"
          />
          <span>
            Send code excerpts to the hosted models ({hosted.map((p) => p.name).join(', ')}).
            <span className="text-muted block">
              Detected secrets are masked first, and the report lists which model saw which file.
              {local.length > 0
                ? ' Without this, only the local model reviews your code.'
                : ' Without this, only static analysis runs.'}
            </span>
          </span>
        </label>
      )}
    </section>
  )
}
