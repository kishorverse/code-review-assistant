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
    <nav className="panel max-h-48 space-y-2 overflow-y-auto p-3 lg:max-h-none" aria-label="Files">
      <h2 className="text-muted text-[13px] font-medium">
        Files{folder && <span className="path font-normal"> in {folder}</span>}
      </h2>
      <ul className="space-y-0.5">
        {files.map((file) => (
          <li key={file.path}>
            <button
              type="button"
              onClick={() => onSelect(file.path)}
              className={`rounded-chip flex w-full items-center gap-2 px-1.5 py-1 text-left text-[13px] ${
                selected === file.path ? 'bg-brand-soft' : 'hover:bg-ink'
              }`}
            >
              <FilePath path={file.path} shown={file.path.slice(folder.length)} />
              {file.findings > 0 && (
                <span className="text-muted ml-auto flex shrink-0 items-center gap-1 tabular-nums">
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
        <details className="text-muted text-[13px]">
          <summary className="cursor-pointer">{skipped.length} files skipped</summary>
          <ul className="mt-1 space-y-0.5">
            {skipped.map((file) => (
              <li key={file.path}>
                <span className="path">{file.path}</span> — {file.reason.replaceAll('_', ' ')}
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
    <span className="path flex min-w-0" title={path}>
      {cut > 0 && <span className="text-muted truncate">{shown.slice(0, cut)}</span>}
      <span className="truncate [flex-shrink:0.01]">{shown.slice(cut)}</span>
    </span>
  )
}
