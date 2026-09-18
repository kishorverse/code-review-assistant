import { FileCode2, Upload } from 'lucide-react'
import { useDropzone } from 'react-dropzone'

const EXTENSIONS = ['.py', '.js', '.jsx', '.ts', '.tsx', '.java', '.go', '.zip']
const MAX_BYTES = 20 * 1024 * 1024

/** Drop zone for a source file or a project archive. */
export function UploadDropzone({
  file,
  onSelect,
}: {
  file: File | null
  onSelect: (file: File) => void
}) {
  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    multiple: false,
    maxSize: MAX_BYTES,
    onDrop: (accepted) => accepted[0] && onSelect(accepted[0]),
  })

  return (
    <div
      {...getRootProps()}
      className={`panel flex cursor-pointer flex-col items-center gap-2 px-6 py-10 text-center transition-colors ${
        isDragActive ? 'border-brand bg-brand-soft' : 'hover:border-brand/60'
      }`}
    >
      <input {...getInputProps()} aria-label="Project file or archive" />
      {file ? (
        <>
          <FileCode2 aria-hidden className="text-brand size-6" />
          <p className="path text-[15px]">{file.name}</p>
          <p className="text-muted text-[13px]">
            {(file.size / 1024).toFixed(0)} kB &middot; choose another file to replace it
          </p>
        </>
      ) : (
        <>
          <Upload aria-hidden className="text-muted size-6" />
          <p className="font-medium">Drop a file or a .zip here, or browse</p>
          <p className="text-muted text-[13px]">{EXTENSIONS.join(' ')} &middot; up to 20 MB</p>
        </>
      )}
    </div>
  )
}
