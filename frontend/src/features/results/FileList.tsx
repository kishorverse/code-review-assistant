import { FileCode2 } from 'lucide-react'

import type { FileEntry, SkippedFile } from '@/lib/api'
import { SEVERITY_DOT } from '@/lib/severity'
import { commonFolder } from '@/lib/text'

/** The scan's files, with how many findings each has. */
export function FileList({
  files,
  skipped,
  selected,
  onSelect,
}: {
  files: FileEntry[]
  skipped: SkippedFile[]
  selected: string | null
  onSelect: (path: string) => void
}) {
  const folder = commonFolder(files.map((file) => file.path))
  return (
    <nav className="flex min-h-0 flex-col" aria-label="Files">
      <div className="border-line flex h-11 shrink-0 items-center gap-2 border-b px-3">
        <h2 className="text-[12.5px] font-semibold">Files</h2>
        {folder && <span className="mono text-faint truncate text-[11.5px]">in {folder}</span>}
        <span className="text-faint ml-auto text-[11.5px] tabular-nums">{files.length}</span>
      </div>
      <ul className="min-h-0 flex-1 overflow-y-auto p-1.5">
        {files.map((file) => (
          <li key={file.path}>
            <button
              type="button"
              onClick={() => onSelect(file.path)}
              className={`rounded-control flex w-full cursor-pointer items-center gap-2 px-2 py-1.5 text-left transition-all duration-200 ${
                selected === file.path
                  ? 'bg-surface text-text shadow-[0_0_0_1px_var(--color-line),0_1px_2px_rgb(0_0_0/0.05)]'
                  : 'text-muted hover:bg-hover hover:text-text'
              }`}
            >
              <FileCode2 aria-hidden className="size-3.5 shrink-0 opacity-70" />
              <FilePath path={file.path} shown={file.path.slice(folder.length)} />
              {file.findings > 0 && (
                <span className="text-faint ml-auto flex shrink-0 items-center gap-1 text-[11.5px] tabular-nums">
                  {file.highest_severity && (
                    <span
                      aria-hidden
                      className={`size-1.5 rounded-full ${SEVERITY_DOT[file.highest_severity]}`}
                    />
                  )}
                  {file.findings}
                </span>
              )}
            </button>
          </li>
        ))}
      </ul>
      {skipped.length > 0 && (
        <details className="border-line text-muted shrink-0 border-t px-3 py-2 text-[12px]">
          <summary className="cursor-pointer select-none">{skipped.length} files skipped</summary>
          <ul className="mt-1.5 max-h-40 space-y-1 overflow-y-auto">
            {skipped.map((file) => (
              <li key={file.path} className="flex gap-2">
                <span className="mono min-w-0 flex-1 truncate">{file.path}</span>
                <span className="text-faint shrink-0">{file.reason.replaceAll('_', ' ')}</span>
              </li>
            ))}
          </ul>
        </details>
      )}
    </nav>
  )
}

/** The folder truncates first, so the file name itself stays readable. */
function FilePath({ path, shown }: { path: string; shown: string }) {
  const cut = shown.lastIndexOf('/') + 1
  return (
    <span className="mono flex min-w-0 text-[12.5px]" title={path}>
      {cut > 0 && <span className="text-faint truncate">{shown.slice(0, cut)}</span>}
      <span className="truncate [flex-shrink:0.01]">{shown.slice(cut)}</span>
    </span>
  )
}
