import { Download } from 'lucide-react'

import { reportUrl, type ReportFormat } from '@/lib/api'

const FORMATS: { format: ReportFormat; label: string }[] = [
  { format: 'html', label: 'HTML' },
  { format: 'json', label: 'JSON' },
  { format: 'sarif', label: 'SARIF' },
]

/** Report downloads. Decisions made here are included. */
export function ReportLinks({ scanId }: { scanId: string }) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="text-muted text-[13px]">
        <Download aria-hidden className="mr-1 inline size-3.5" />
        Download report
      </span>
      {FORMATS.map(({ format, label }) => (
        <a
          key={format}
          href={reportUrl(scanId, format)}
          className="rounded-control border-line hover:border-brand border px-2 py-1 text-[13px]"
        >
          {label}
        </a>
      ))}
    </div>
  )
}
