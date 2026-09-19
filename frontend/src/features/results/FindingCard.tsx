import { Check, Lightbulb, RotateCcw, ShieldCheck, Sparkles, Wrench, X } from 'lucide-react'
import type { ReactNode } from 'react'

import { Button } from '@/components/ui/button'
import type { Decision, Finding } from '@/lib/api'
import { SEVERITY_DOT, SEVERITY_LABEL, STATUS_LABEL, hasModelSource, isModel } from '@/lib/severity'
import { dedent } from '@/lib/text'

const SEVERITY_TEXT: Record<Finding['severity'], string> = {
  critical: 'text-critical',
  high: 'text-high',
  medium: 'text-medium',
  low: 'text-low',
  info: 'text-info',
}

const STATUS_TONE: Record<string, string> = {
  accepted: 'text-success border-success/30 bg-success/8',
  rejected: 'text-muted border-line bg-subtle',
  dismissed_by_ai: 'text-muted border-line bg-subtle',
  needs_review: 'text-medium border-medium/30 bg-medium/8',
}

/**
 * One finding in the list. Collapsed it names the problem and where it is; selected it
 * explains why it matters, what to change, who found it, and takes a decision.
 */
export function FindingCard({
  finding,
  selected,
  onSelect,
  onDecide,
}: {
  finding: Finding
  selected: boolean
  onSelect: () => void
  onDecide: (status: Decision) => void
}) {
  const muted = finding.status === 'dismissed_by_ai' || finding.status === 'rejected'
  const fileName = finding.file_path.slice(finding.file_path.lastIndexOf('/') + 1)
  const fromModel = hasModelSource(finding)
  const fromTool = finding.sources.some((source) => !isModel(source))

  return (
    <article
      id={`finding-${finding.id}`}
      aria-current={selected}
      className={`border-line/70 relative border-b transition-colors duration-300 ${
        selected ? 'bg-accent-soft/40' : 'hover:bg-subtle/70'
      }`}
    >
      <span
        aria-hidden
        className={`ease-out-expo absolute inset-y-0 left-0 w-[3px] origin-top bg-[linear-gradient(180deg,var(--color-accent),var(--color-accent-2))] transition-transform duration-500 ${
          selected ? 'scale-y-100' : 'scale-y-0'
        }`}
      />
      <button
        type="button"
        onClick={onSelect}
        aria-expanded={selected}
        className={`flex w-full cursor-pointer gap-3 px-4 py-3.5 text-left ${muted ? 'opacity-55' : ''}`}
      >
        <span
          aria-hidden
          className={`mt-[7px] size-2 shrink-0 rounded-full ${SEVERITY_DOT[finding.severity]}`}
        />
        <span className="min-w-0 flex-1">
          <span
            className={`block text-[13px] leading-snug ${selected ? 'font-semibold' : 'font-medium'} ${
              selected ? '' : 'line-clamp-2'
            }`}
          >
            {finding.title}
          </span>
          <span className="text-faint mt-1 flex items-center gap-1.5 text-[11.5px]">
            <span className={`shrink-0 font-medium ${SEVERITY_TEXT[finding.severity]}`}>
              {SEVERITY_LABEL[finding.severity]}
            </span>
            <span aria-hidden>·</span>
            <span className="mono min-w-0 truncate" title={finding.file_path}>
              {fileName}:{finding.start_line}
            </span>
            <span aria-hidden>·</span>
            <span className="shrink-0 capitalize">{finding.category}</span>
            <span className="ml-auto flex shrink-0 items-center gap-1">
              {fromTool && (
                <Wrench aria-label="Found by an analyzer" className="size-3 opacity-70" />
              )}
              {fromModel && (
                <Sparkles aria-label="Found by a model" className="text-accent-text size-3" />
              )}
              {finding.verified_by.length > 0 && (
                <ShieldCheck
                  aria-label="Verified by a second model"
                  className="text-success size-3"
                />
              )}
              {finding.status !== 'open' && (
                <span
                  className={`ml-0.5 rounded-full border px-1.5 text-[10.5px] leading-[16px] font-medium ${STATUS_TONE[finding.status] ?? ''}`}
                >
                  {STATUS_LABEL[finding.status]}
                </span>
              )}
            </span>
          </span>
        </span>
      </button>

      {selected && <Details finding={finding} onDecide={onDecide} />}
    </article>
  )
}

function Details({
  finding,
  onDecide,
}: {
  finding: Finding
  onDecide: (status: Decision) => void
}) {
  const decided = finding.status === 'accepted' || finding.status === 'rejected'
  return (
    <div className="animate-expand space-y-3.5 px-4 pb-5 pl-9 text-[13.5px] leading-relaxed">
      {finding.message.trim() !== finding.title.trim() && (
        <p className="text-text">{finding.message}</p>
      )}
      {finding.rationale && (
        <p className="text-muted">
          <strong className="text-text font-medium">Why it matters: </strong>
          {finding.rationale}
        </p>
      )}
      {finding.evidence && (
        <pre className="border-line bg-subtle overflow-x-auto rounded-[10px] border px-3.5 py-2.5 text-[12px] leading-5">
          <code>{dedent(finding.evidence)}</code>
        </pre>
      )}
      {finding.suggestion && (
        <div className="border-success/25 bg-success/5 rounded-[10px] border px-3.5 py-2.5">
          <p className="text-success flex items-center gap-1.5 text-[11.5px] font-medium">
            <Lightbulb aria-hidden className="size-3" />
            Suggested change
          </p>
          <p className="mt-0.5">{finding.suggestion}</p>
        </div>
      )}
      {finding.ai_note && (
        <p className="border-line-strong text-muted border-l-2 pl-3 text-[12.5px]">
          {finding.ai_note}
        </p>
      )}

      <dl className="border-line grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 border-t pt-3 text-[12.5px]">
        <Fact term="Found by">
          <Sources names={finding.sources} />
        </Fact>
        {finding.verified_by.length > 0 && (
          <Fact term="Verified by">
            <Sources names={finding.verified_by} />
          </Fact>
        )}
        <Fact term="Confidence">
          <Confidence value={finding.confidence} />
        </Fact>
        {(finding.cwe || finding.rule_id) && (
          <Fact term="Reference">
            <span className="mono text-[12px]">
              {[finding.cwe, finding.rule_id].filter(Boolean).join(' · ')}
            </span>
          </Fact>
        )}
      </dl>

      <div className="flex items-center gap-2 pt-1">
        {decided ? (
          <Button size="sm" onClick={() => onDecide('open')}>
            <RotateCcw aria-hidden />
            Restore
          </Button>
        ) : (
          <>
            <Button size="sm" onClick={() => onDecide('accepted')}>
              <Check aria-hidden className="text-success" />
              Accept
            </Button>
            <Button size="sm" onClick={() => onDecide('rejected')}>
              <X aria-hidden className="text-critical" />
              Reject
            </Button>
          </>
        )}
      </div>
    </div>
  )
}

function Fact({ term, children }: { term: string; children: ReactNode }) {
  return (
    <>
      <dt className="text-faint">{term}</dt>
      <dd className="min-w-0">{children}</dd>
    </>
  )
}

function Sources({ names }: { names: string[] }) {
  return (
    <span className="flex flex-wrap gap-1">
      {names.map((name) => (
        <span
          key={name}
          className={`mono rounded-[4px] border px-1.5 text-[11.5px] leading-[18px] ${
            isModel(name)
              ? 'border-accent/25 bg-accent-soft text-accent-text'
              : 'border-line bg-subtle'
          }`}
        >
          {name}
        </span>
      ))}
    </span>
  )
}

function Confidence({ value }: { value: number }) {
  return (
    <span className="flex items-center gap-2">
      <span className="bg-subtle h-1 w-20 overflow-hidden rounded-full" aria-hidden>
        <span
          className="block h-full origin-left rounded-full bg-[linear-gradient(90deg,var(--color-accent),var(--color-accent-2))] [animation:grow-x_900ms_var(--ease-out-expo)_both]"
          style={{ width: `${Math.round(value * 100)}%` }}
        />
      </span>
      <span className="tabular-nums">{value.toFixed(2)}</span>
    </span>
  )
}
