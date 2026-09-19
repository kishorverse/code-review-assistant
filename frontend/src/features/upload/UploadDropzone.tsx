import { Check, FileArchive, FileCode2, UploadCloud } from 'lucide-react'
import { useDropzone } from 'react-dropzone'

const EXTENSIONS = ['.py', '.js', '.jsx', '.ts', '.tsx', '.java', '.go', '.zip']
const MAX_BYTES = 20 * 1024 * 1024

function size(bytes: number): string {
  return bytes < 1024 * 1024
    ? `${Math.max(1, Math.round(bytes / 1024))} KB`
    : `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

/** Drop zone for a source file or a project archive. */
export function UploadDropzone({
  file,
  onSelect,
}: {
  file: File | null
  onSelect: (file: File) => void
}) {
  const { getRootProps, getInputProps, isDragActive, open } = useDropzone({
    multiple: false,
    maxSize: MAX_BYTES,
    noClick: file !== null,
    onDrop: (accepted) => accepted[0] && onSelect(accepted[0]),
  })

  if (file) {
    const Icon = file.name.endsWith('.zip') ? FileArchive : FileCode2
    return (
      <div
        {...getRootProps()}
        key={file.name + file.size}
        className={`rise flex items-center gap-3.5 rounded-[12px] border px-3.5 py-3 transition-colors duration-300 ${
          isDragActive ? 'border-accent bg-accent-soft' : 'border-line bg-surface'
        }`}
      >
        <input {...getInputProps()} aria-label="Project file or archive" />
        <span className="relative">
          <span className="bg-accent-soft text-accent-text grid size-10 place-items-center rounded-[10px]">
            <Icon aria-hidden className="size-[18px]" />
          </span>
          <span className="bg-success ring-surface absolute -right-1 -bottom-1 grid size-4 place-items-center rounded-full ring-2 [animation:rise_500ms_var(--ease-spring)_200ms_both]">
            <Check aria-hidden className="size-2.5 text-white" strokeWidth={3} />
          </span>
        </span>
        <div className="min-w-0 flex-1">
          <p className="mono truncate text-[13px] font-medium">{file.name}</p>
          <p className="text-faint text-[12px]">{size(file.size)} · ready to scan</p>
        </div>
        <button
          type="button"
          onClick={open}
          className="rounded-control border-line bg-surface hover:bg-subtle hover:border-line-strong h-7 cursor-pointer border px-2.5 text-[12.5px] font-medium transition-colors active:scale-[0.97]"
        >
          Replace
        </button>
      </div>
    )
  }

  return (
    <div
      {...getRootProps()}
      className={`group relative flex cursor-pointer flex-col items-center gap-3 overflow-hidden rounded-[12px] border border-dashed px-6 py-10 text-center transition-all duration-300 ease-out-expo ${
        isDragActive
          ? 'border-accent bg-accent-soft scale-[1.01]'
          : 'border-line-strong bg-subtle/50 hover:border-accent/50 hover:bg-accent-soft/40'
      }`}
    >
      <input {...getInputProps()} aria-label="Project file or archive" />
      <div
        aria-hidden
        className="bg-grid pointer-events-none absolute inset-0 opacity-0 transition-opacity duration-500 group-hover:opacity-100"
      />
      <span
        className={`border-line bg-surface text-accent-text relative grid size-12 place-items-center rounded-[14px] border shadow-[0_4px_14px_-4px_rgb(0_0_0/0.12)] transition-transform duration-500 ease-spring ${
          isDragActive ? '-translate-y-1 scale-110' : 'animate-float group-hover:scale-105'
        }`}
      >
        <UploadCloud aria-hidden className="size-5" />
      </span>
      <p className="relative text-[14px]">
        <span className="font-medium">
          {isDragActive ? 'Release to add it' : 'Drop a file or a .zip here'}
        </span>
        {!isDragActive && (
          <>
            <span className="text-muted"> or </span>
            <span className="text-accent-text font-medium underline decoration-current/30 underline-offset-4 transition-colors group-hover:decoration-current">
              browse
            </span>
          </>
        )}
      </p>
      <p className="text-faint relative flex flex-wrap justify-center gap-1 text-[11.5px]">
        {EXTENSIONS.map((extension) => (
          <span
            key={extension}
            className="mono border-line bg-surface rounded-[5px] border px-1.5 py-px"
          >
            {extension}
          </span>
        ))}
        <span className="ml-1 self-center">up to 20 MB</span>
      </p>
    </div>
  )
}
