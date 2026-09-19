import { Download } from 'lucide-react'

import { reportUrl, type ReportFormat } from '@/lib/api'

const FORMATS: { format: ReportFormat; label: string; title: string }[] = [
  { format: 'html', label: 'HTML', title: 'A self-contained report to read or share' },
  { format: 'json', label: 'JSON', title: 'Every finding and model call, for tools' },
  { format: 'sarif', label: 'SARIF', title: 'For GitHub code scanning and IDEs' },
]

/** Report downloads, as one segmented control. Decisions made here are included. */
export function ReportLinks({ scanId }: { scanId: string }) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-muted hidden items-center gap-1.5 text-[12.5px] sm:inline-flex">
        <Download aria-hidden className="size-3.5" />
        Report
      </span>
      <div className="border-line bg-surface divide-line inline-flex divide-x overflow-hidden rounded-control border shadow-[0_1px_2px_rgb(0_0_0/0.04)]">
        {FORMATS.map(({ format, label, title }) => (
          <a
            key={format}
            href={reportUrl(scanId, format)}
            title={title}
            className="hover:bg-subtle hover:text-accent-text h-8 px-3 text-[12.5px] leading-8 font-medium transition-colors"
          >
            {label}
          </a>
        ))}
      </div>
    </div>
  )
}
