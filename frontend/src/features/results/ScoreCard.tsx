import type { QualityScore } from '@/lib/api'

/** The quality score, with the formula that produced it. */
export function ScoreCard({ score }: { score: QualityScore }) {
  return (
    <section className="panel space-y-1 p-4">
      <h2 className="text-muted text-[13px] font-medium">Quality score</h2>
      <p className="font-display text-[48px] leading-none">
        {score.score}
        <span className="text-muted text-[18px]"> / 100 &middot; {score.grade}</span>
      </p>
      <details className="text-muted text-[13px]">
        <summary className="cursor-pointer">How this is calculated</summary>
        <p className="mt-1">{score.formula}</p>
        <p className="mt-1">
          {score.kloc.toFixed(2)} thousand lines &middot; finding penalty {score.finding_penalty}
          &middot; complexity penalty {score.complexity_penalty} ({score.complex_functions} of{' '}
          {score.functions} functions)
        </p>
      </details>
    </section>
  )
}
