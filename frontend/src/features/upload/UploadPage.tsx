import { useMutation, useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useNavigate } from 'react-router'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { DepthPicker } from '@/features/upload/DepthPicker'
import { ProviderPanel } from '@/features/upload/ProviderPanel'
import { UploadDropzone } from '@/features/upload/UploadDropzone'
import { ApiError, createScan, getProviders, type Depth } from '@/lib/api'

/** Landing page: choose what to scan, how deeply, and whether hosted models may see it. */
export function UploadPage() {
  const navigate = useNavigate()
  const [file, setFile] = useState<File | null>(null)
  const [depth, setDepth] = useState<Depth>('standard')
  const [allowExternal, setAllowExternal] = useState(false)
  const providers = useQuery({ queryKey: ['providers'], queryFn: getProviders })

  const scan = useMutation({
    mutationFn: createScan,
    onSuccess: (created) => navigate(`/scans/${created.id}`),
    onError: (error) =>
      toast.error(
        error instanceof ApiError ? error.message : 'The upload failed. Please try again.',
      ),
  })

  const hasHosted = providers.data?.providers.some((provider) => provider.external) ?? false
  const hasLocal = providers.data?.providers.some((provider) => !provider.external) ?? false
  const usesModels = depth !== 'static' && (allowExternal ? hasHosted || hasLocal : hasLocal)

  return (
    <div className="mx-auto grid max-w-5xl gap-8 px-6 py-10 lg:grid-cols-[1.4fr_1fr]">
      <div className="space-y-6">
        <header className="space-y-2">
          <h1 className="text-[32px] leading-tight sm:text-[48px]">
            Code review that shows its work.
          </h1>
          <p className="text-muted max-w-[60ch] text-[18px]">
            Analyzers find it, models check it, and every finding cites the exact lines it came
            from. You decide what changes.
          </p>
        </header>

        <UploadDropzone file={file} onSelect={setFile} />
        <DepthPicker depth={depth} onChange={setDepth} />

        <div className="flex flex-wrap items-center gap-3">
          <Button
            disabled={!file || scan.isPending}
            onClick={() => file && scan.mutate({ file, depth, allowExternal })}
          >
            {scan.isPending ? 'Uploading…' : 'Scan project'}
          </Button>
          <p className="text-muted text-[13px]">
            {depth === 'static'
              ? 'Static analysis only: no model sees your code.'
              : usesModels
                ? allowExternal
                  ? 'Hosted models will review masked excerpts of your code.'
                  : 'Only a model on this machine will review your code.'
                : 'No model is available, so this runs static analysis only.'}
          </p>
        </div>
      </div>

      <ProviderPanel
        providers={providers.data}
        allowExternal={allowExternal}
        onAllowExternal={setAllowExternal}
        disabled={depth === 'static'}
      />
    </div>
  )
}
