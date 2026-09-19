import { ArrowRight, Sparkles } from 'lucide-react'
import type { CSSProperties, ReactNode } from 'react'

import type { Finding, ScanDetail } from '@/lib/api'
import { SEVERITIES, SEVERITY_DOT, SEVERITY_LABEL, countBySeverity } from '@/lib/severity'
import { stagger } from '@/lib/utils'

const TONE: Record<string, string> = {
  A: 'var(--color-success)',
  B: 'var(--color-low)',
  C: 'var(--color-medium)',
  D: 'var(--color-high)',
  E: 'var(--color-critical)',
}

const GRADE: Record<string, string> = {
  A: 'bg-success/10 text-success border-success/25',
  B: 'bg-low/10 text-low border-low/25',
  C: 'bg-medium/10 text-medium border-medium/30',
  D: 'bg-high/10 text-high border-high/25',
  E: 'bg-critical/10 text-critical border-critical/25',
}

/** The review at a glance, in one row: score, findings, coverage and the models' headline. */
export function ResultsOverview({
  detail,
  reported,
  onOpenSummary,
}: {
  detail: ScanDetail
  reported: Finding[]
  onOpenSummary: () => void
}) {
  const { score, summary, ai_summary: aiSummary, calls } = detail
  const answered = calls.filter((call) => call.status === 'ok' || call.status === 'cached').length
  return (
    <section
      className="rise panel divide-line grid overflow-hidden max-md:divide-y md:grid-cols-[auto_auto_minmax(0,1fr)] md:divide-x"
      style={stagger(0)}
      aria-label="Review overview"
    >
      {score && (
        <Segment>
          <ScoreRing score={score.score} tone={TONE[score.grade] ?? TONE.C ?? ''} />
          <div className="min-w-0">
            <p className="eyebrow">Quality score</p>
            <div className="mt-1 flex items-center gap-2">
              <p className="text-[22px] leading-none font-semibold tracking-tight tabular-nums">
                {score.score}
              </p>
              <span className="text-faint text-[12px]">/ 100</span>
              <span
                aria-label={`Grade ${score.grade}`}
                title={score.formula}
                className={`grid size-6 place-items-center rounded-md border text-[12px] font-semibold ${GRADE[score.grade] ?? GRADE.C}`}
              >
                {score.grade}
              </span>
            </div>
          </div>
        </Segment>
      )}

      <Segment>
        <div className="min-w-0">
          <p className="eyebrow">Findings</p>
          <div className="mt-1 flex items-baseline gap-2">
            <span className="text-[22px] leading-none font-semibold tracking-tight tabular-nums">
              {reported.length}
            </span>
            <span className="text-faint text-[12px]">in the report</span>
          </div>
          <SeverityLine findings={reported} />
          <p className="text-faint mt-1.5 text-[11.5px] whitespace-nowrap">
            {[
              summary
                ? `${summary.files_scanned} ${summary.files_scanned === 1 ? 'file' : 'files'}`
                : null,
              summary ? `${summary.files_reviewed} read by a model` : null,
              calls.length > 0 ? `${answered} of ${calls.length} model calls answered` : null,
            ]
              .filter(Boolean)
              .join(' · ')}
          </p>
        </div>
      </Segment>

      <div className="flex min-w-0 items-center gap-4 px-5 py-3.5">
        <div className="min-w-0 flex-1">
          <p className="eyebrow flex items-center gap-1.5">
            <Sparkles aria-hidden className="text-accent-text size-3" />
            AI summary
          </p>
          {aiSummary ? (
            <p className="mt-1 line-clamp-2 text-[14px] leading-snug font-medium text-pretty">
              {aiSummary.headline}
            </p>
          ) : (
            <p className="text-muted mt-1 text-[13px]">
              No model summary for this review: it ran the static analyzers only.
            </p>
          )}
        </div>
        <button
          type="button"
          onClick={onOpenSummary}
          className="group text-accent-text hover:bg-accent-soft rounded-control inline-flex h-8 shrink-0 cursor-pointer items-center gap-1 px-2.5 text-[12.5px] font-medium transition-colors"
        >
          Full summary
          <ArrowRight
            aria-hidden
            className="size-3.5 transition-transform duration-300 group-hover:translate-x-0.5"
          />
        </button>
      </div>
    </section>
  )
}

function Segment({ children }: { children: ReactNode }) {
  return <div className="flex items-center gap-3.5 px-5 py-3.5">{children}</div>
}

const RADIUS = 20
const CIRCUMFERENCE = 2 * Math.PI * RADIUS

function ScoreRing({ score, tone }: { score: number; tone: string }) {
  const offset = CIRCUMFERENCE * (1 - Math.max(0, Math.min(100, score)) / 100)
  return (
    <svg viewBox="0 0 48 48" className="size-11 shrink-0 -rotate-90" aria-hidden>
      <circle cx="24" cy="24" r={RADIUS} fill="none" strokeWidth="5" className="stroke-subtle" />
      <circle
        cx="24"
        cy="24"
        r={RADIUS}
        fill="none"
        strokeWidth="5"
        strokeLinecap="round"
        stroke={tone}
        strokeDasharray={CIRCUMFERENCE}
        strokeDashoffset={offset}
        style={
          {
            '--from': CIRCUMFERENCE,
            animation: 'draw 1200ms var(--ease-out-expo) 150ms both',
          } as CSSProperties
        }
      />
    </svg>
  )
}

function SeverityLine({ findings }: { findings: Finding[] }) {
  const counts = countBySeverity(findings)
  const total = findings.length
  return (
    <div className="mt-2 space-y-1.5">
      <div className="bg-subtle flex h-1.5 w-44 gap-px overflow-hidden rounded-full" aria-hidden>
        {total > 0 &&
          SEVERITIES.map((severity) =>
            counts[severity] > 0 ? (
              <span
                key={severity}
                className={`${SEVERITY_DOT[severity]} ease-out-expo transition-[width] duration-700`}
                style={{ width: `${(counts[severity] / total) * 100}%` }}
              />
            ) : null,
          )}
      </div>
      <ul className="flex gap-2.5 text-[11px]">
        {SEVERITIES.filter((severity) => counts[severity] > 0).map((severity) => (
          <li key={severity} className="flex items-center gap-1" title={SEVERITY_LABEL[severity]}>
            <span aria-hidden className={`size-1.5 rounded-full ${SEVERITY_DOT[severity]}`} />
            <span className="text-muted">{SEVERITY_LABEL[severity]}</span>
            <span className="font-medium tabular-nums">{counts[severity]}</span>
          </li>
        ))}
        {total === 0 && <li className="text-success font-medium">No findings</li>}
      </ul>
    </div>
  )
}
