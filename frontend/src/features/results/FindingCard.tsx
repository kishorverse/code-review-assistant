import { Check, X } from 'lucide-react'

import { SeverityChip } from '@/components/SeverityChip'
import type { Decision, Finding } from '@/lib/api'
import { STATUS_LABEL } from '@/lib/severity'
import { dedent } from '@/lib/text'

/** One finding: what, where, who found it, why it matters and what to do. */
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
  return (
    <article
      id={`finding-${finding.id}`}
      aria-current={selected}
      onClick={onSelect}
      className={`panel cursor-pointer space-y-2 p-3 ${selected ? 'border-brand' : ''} ${
        muted ? 'opacity-60' : ''
      }`}
    >
      <header className="flex flex-wrap items-baseline gap-2">
        <SeverityChip severity={finding.severity} />
        <h3 className="text-[15px] font-medium">{finding.title}</h3>
      </header>

      <p className="text-muted flex flex-wrap gap-x-3 gap-y-1 text-[13px]">
        <span className="path">
          {finding.file_path}:{finding.start_line}
        </span>
        <span>{finding.category}</span>
        {finding.cwe && <span>{finding.cwe}</span>}
        <span>Found by {finding.sources.join(', ')}</span>
        {finding.verified_by.length > 0 && (
          <span>Verified by {finding.verified_by.join(', ')}</span>
        )}
        <span>Confidence {finding.confidence.toFixed(2)}</span>
        {finding.status !== 'open' && (
          <span className="font-medium">{STATUS_LABEL[finding.status]}</span>
        )}
      </p>

      {finding.message.trim() !== finding.title.trim() && <p>{finding.message}</p>}
      {finding.rationale && (
        <p className="text-muted text-[13px]">
          <strong className="text-text">Why it matters: </strong>
          {finding.rationale}
        </p>
      )}
      {finding.evidence && (
        <pre className="bg-ink rounded-chip overflow-x-auto p-2 text-[13px]">
          <code>{dedent(finding.evidence)}</code>
        </pre>
      )}
      {finding.suggestion && (
        <p className="text-[13px]">
          <strong>Suggested change: </strong>
          {finding.suggestion}
        </p>
      )}
      {finding.ai_note && (
        <p className="border-brand text-muted border-l-2 pl-2 text-[13px]">{finding.ai_note}</p>
      )}

      <div className="flex gap-2 pt-1">
        {finding.status === 'accepted' || finding.status === 'rejected' ? (
          <Action label="Restore" onClick={() => onDecide('open')} />
        ) : (
          <>
            <Action
              label="Accept"
              icon={<Check aria-hidden className="size-3.5" />}
              onClick={() => onDecide('accepted')}
            />
            <Action
              label="Reject"
              icon={<X aria-hidden className="size-3.5" />}
              onClick={() => onDecide('rejected')}
            />
          </>
        )}
      </div>
    </article>
  )
}

function Action({
  label,
  icon,
  onClick,
}: {
  label: string
  icon?: React.ReactNode
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={(event) => {
        event.stopPropagation()
        onClick()
      }}
      className="rounded-control border-line hover:border-brand inline-flex items-center gap-1 border px-2 py-1 text-[13px]"
    >
      {icon}
      {label}
    </button>
  )
}
