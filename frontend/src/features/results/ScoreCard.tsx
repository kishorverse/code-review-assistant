import type { CSSProperties } from 'react'

import type { QualityScore } from '@/lib/api'
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

const RADIUS = 42
const CIRCUMFERENCE = 2 * Math.PI * RADIUS

/** The quality score as a ring that fills on arrival, with the formula that produced it. */
export function ScoreCard({ score }: { score: QualityScore }) {
  const tone = TONE[score.grade] ?? TONE.C
  const offset = CIRCUMFERENCE * (1 - Math.max(0, Math.min(100, score.score)) / 100)
  return (
    <section className="rise panel flex flex-col px-5 py-4.5" style={stagger(0)}>
      <div className="flex items-center">
        <h2 className="eyebrow">Quality score</h2>
        <span
          className={`ml-auto grid size-7 place-items-center rounded-lg border text-[13px] font-semibold ${GRADE[score.grade] ?? GRADE.C}`}
          aria-label={`Grade ${score.grade}`}
        >
          {score.grade}
        </span>
      </div>

      <div className="mt-3 flex items-center gap-5">
        <div
          role="meter"
          aria-label="Quality score"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={score.score}
          className="relative size-[104px] shrink-0"
        >
          <svg viewBox="0 0 100 100" className="size-full -rotate-90" aria-hidden>
            <circle
              cx="50"
              cy="50"
              r={RADIUS}
              fill="none"
              strokeWidth="7"
              className="stroke-subtle"
            />
            <circle
              cx="50"
              cy="50"
              r={RADIUS}
              fill="none"
              strokeWidth="7"
              strokeLinecap="round"
              stroke={tone}
              strokeDasharray={CIRCUMFERENCE}
              strokeDashoffset={offset}
              style={
                {
                  '--from': CIRCUMFERENCE,
                  animation: 'draw 1400ms var(--ease-out-expo) 200ms both',
                  filter: `drop-shadow(0 0 6px color-mix(in srgb, ${tone} 45%, transparent))`,
                } as CSSProperties
              }
            />
          </svg>
          <div className="absolute inset-0 grid place-content-center text-center">
            <p className="text-[30px] leading-none font-semibold tracking-tight tabular-nums">
              {score.score}
            </p>
            <span className="text-faint mt-1 text-[11px]">of 100</span>
          </div>
        </div>
        <dl className="min-w-0 space-y-2 text-[12.5px]">
          <Stat term="KLOC" value={score.kloc.toFixed(2)} />
          <Stat term="Functions" value={score.functions} />
          <Stat term="Complex" value={score.complex_functions} />
        </dl>
      </div>

      <details className="group mt-auto pt-3">
        <summary className="text-accent-text flex cursor-pointer list-none items-center gap-1 text-[12.5px] font-medium select-none">
          <span className="transition-transform duration-300 group-open:rotate-90">›</span>
          How this is calculated
        </summary>
        <div className="animate-expand">
          <p className="text-muted mt-1.5 text-[12.5px] leading-relaxed">{score.formula}</p>
          <p className="text-muted mt-1 text-[12.5px]">
            Finding penalty {score.finding_penalty} · complexity penalty {score.complexity_penalty}
          </p>
        </div>
      </details>
    </section>
  )
}

function Stat({ term, value }: { term: string; value: string | number }) {
  return (
    <div className="flex items-baseline gap-2">
      <dt className="text-faint w-16">{term}</dt>
      <dd className="font-medium tabular-nums">{value}</dd>
    </div>
  )
}
