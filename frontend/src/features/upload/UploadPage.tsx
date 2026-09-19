import { useMutation, useQuery } from '@tanstack/react-query'
import { ArrowRight, FileJson2, Info, LoaderCircle, ScanSearch, Sparkles } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { useNavigate } from 'react-router'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { DepthPicker } from '@/features/upload/DepthPicker'
import { ProviderPanel } from '@/features/upload/ProviderPanel'
import { UploadDropzone } from '@/features/upload/UploadDropzone'
import { ApiError, createScan, getProviders, type Depth } from '@/lib/api'
import { rememberScan } from '@/lib/recent'
import { stagger } from '@/lib/utils'

const HIGHLIGHTS = [
  { icon: ScanSearch, title: 'Eight analyzers', text: 'Lint, types, security and complexity' },
  { icon: Sparkles, title: 'Models cross-check', text: 'A second model verifies serious finds' },
  { icon: FileJson2, title: 'Reports that travel', text: 'HTML, JSON and SARIF for GitHub' },
]

/** Start a review: what to scan, how deeply, and whether hosted models may see it. */
export function UploadPage() {
  const navigate = useNavigate()
  const [file, setFile] = useState<File | null>(null)
  const [depth, setDepth] = useState<Depth>('standard')
  const [allowExternal, setAllowExternal] = useState(false)
  const providers = useQuery({ queryKey: ['providers'], queryFn: getProviders })

  const scan = useMutation({
    mutationFn: createScan,
    onSuccess: (created) => {
      rememberScan({ id: created.id, source: created.source, createdAt: created.created_at })
      navigate(`/scans/${created.id}`)
    },
    onError: (error) =>
      toast.error(
        error instanceof ApiError ? error.message : 'The upload failed. Please try again.',
      ),
  })

  const hasHosted = providers.data?.providers.some((provider) => provider.external) ?? false
  const hasLocal = providers.data?.providers.some((provider) => !provider.external) ?? false
  const usesModels = depth !== 'static' && (allowExternal ? hasHosted || hasLocal : hasLocal)
  const outcome =
    depth === 'static'
      ? 'Static analysis only: no model sees your code.'
      : usesModels
        ? allowExternal
          ? 'Hosted models will review masked excerpts of your code.'
          : 'Only a model on this machine will review your code.'
        : 'No model is available, so this runs static analysis only.'

  return (
    <div className="relative">
      <Backdrop />

      <div className="relative mx-auto max-w-5xl px-5 pt-14 pb-16 sm:px-8 lg:pt-20">
        <section className="mx-auto max-w-3xl text-center">
          <h1
            className="rise display text-[44px] leading-[1.02] tracking-[-0.02em] text-balance sm:text-[60px]"
            style={stagger(0)}
          >
            Code review with a{' '}
            <em className="text-gradient pr-1 whitespace-nowrap">second opinion</em>
          </h1>
          <p
            className="rise text-muted mx-auto mt-5 max-w-xl text-[15px] leading-relaxed text-pretty"
            style={stagger(1)}
          >
            Static analyzers run first; models then judge what they found and look for what no rule
            can.
          </p>
        </section>

        <ul className="mx-auto mt-10 grid max-w-3xl gap-3 sm:grid-cols-3">
          {HIGHLIGHTS.map(({ icon: Icon, title, text }, index) => (
            <li
              key={title}
              className="rise group border-line/80 bg-surface/60 flex items-start gap-3 rounded-[12px] border px-3.5 py-3 backdrop-blur transition-[border-color,transform] duration-300 hover:-translate-y-0.5 hover:border-line-strong"
              style={stagger(index + 2)}
            >
              <span className="border-line bg-surface text-accent-text grid size-8 shrink-0 place-items-center rounded-lg border shadow-[0_1px_2px_rgb(0_0_0/0.04)] transition-transform duration-500 ease-spring group-hover:scale-110 group-hover:-rotate-6">
                <Icon aria-hidden className="size-4" />
              </span>
              <span className="min-w-0">
                <span className="block text-[13px] font-medium">{title}</span>
                <span className="text-faint block text-[12px] leading-snug">{text}</span>
              </span>
            </li>
          ))}
        </ul>

        <form
          className="rise panel ring-gradient shadow-lift mt-12 overflow-visible"
          style={stagger(6)}
          onSubmit={(event) => {
            event.preventDefault()
            if (file) scan.mutate({ file, depth, allowExternal })
          }}
        >
          <Step
            number={1}
            title="Source"
            description="A single source file, or a project as a .zip. Dependencies, build output and binaries are skipped."
            done={file !== null}
          >
            <UploadDropzone file={file} onSelect={setFile} />
          </Step>
          <Step
            number={2}
            title="Review depth"
            description="How much the models do. Deeper reviews make more calls and take longer."
            done
          >
            <DepthPicker depth={depth} onChange={setDepth} />
          </Step>
          <Step
            number={3}
            title="Models and data"
            description="The models this server is configured with. Hosted ones receive code only with your consent."
            done={providers.isSuccess}
          >
            <ProviderPanel
              providers={providers.data}
              allowExternal={allowExternal}
              onAllowExternal={setAllowExternal}
              disabled={depth === 'static'}
            />
          </Step>
          <div className="bg-subtle/60 flex flex-wrap items-center gap-4 rounded-b-[inherit] px-5 py-4 sm:px-7">
            <p
              key={outcome}
              className="fade-in text-muted flex min-w-0 flex-1 items-center gap-2 text-[12.5px]"
            >
              <Info aria-hidden className="text-accent-text size-3.5 shrink-0" />
              {outcome}
            </p>
            <Button
              type="submit"
              variant="primary"
              size="lg"
              disabled={!file || scan.isPending}
              className="w-full sm:w-auto"
            >
              {scan.isPending ? (
                <>
                  <LoaderCircle aria-hidden className="animate-spin" />
                  Uploading…
                </>
              ) : (
                <>
                  Scan project
                  <ArrowRight aria-hidden />
                </>
              )}
            </Button>
          </div>
        </form>

        <p className="rise text-faint mt-6 text-center text-[12px]" style={stagger(8)}>
          Uploads are kept for a limited time only. Detected secrets are masked before any model
          sees them.
        </p>
      </div>
    </div>
  )
}

/** Soft colour and a dotted grid behind the hero, fading into the page. */
function Backdrop() {
  return (
    <div
      aria-hidden
      className="pointer-events-none absolute inset-x-0 top-0 h-[640px] overflow-hidden"
    >
      <div className="bg-grid absolute inset-0" />
      <div className="bg-accent/15 absolute -top-48 left-1/2 size-[640px] -translate-x-[70%] rounded-full blur-[120px]" />
      <div className="bg-accent-2/15 absolute -top-40 left-1/2 size-[520px] -translate-x-[10%] rounded-full blur-[120px]" />
      <div className="to-canvas absolute inset-x-0 bottom-0 h-40 bg-gradient-to-b from-transparent" />
    </div>
  )
}

function Step({
  number,
  title,
  description,
  done,
  children,
}: {
  number: number
  title: string
  description: string
  done: boolean
  children: ReactNode
}) {
  return (
    <section className="border-line grid gap-5 border-b px-5 py-7 sm:px-7 md:grid-cols-[240px_1fr] md:gap-10">
      <div className="flex gap-3.5 md:block">
        <span
          className={`mono grid size-7 shrink-0 place-items-center rounded-full border text-[11px] font-medium transition-all duration-500 ease-spring ${
            done
              ? 'border-accent/30 bg-accent-soft text-accent-text'
              : 'border-line text-faint bg-surface'
          }`}
        >
          {String(number).padStart(2, '0')}
        </span>
        <div className="md:mt-4">
          <h2 className="text-[14.5px] font-semibold tracking-tight">{title}</h2>
          <p className="text-muted mt-1.5 text-[12.5px] leading-relaxed">{description}</p>
        </div>
      </div>
      <div className="min-w-0">{children}</div>
    </section>
  )
}
