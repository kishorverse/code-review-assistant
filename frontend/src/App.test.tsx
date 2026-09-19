import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import App from '@/App'
import type { ScanStatus } from '@/lib/api'
import { useScanStore } from '@/store/scan-store'
import { FakeEventSource, makeDetail, makeFinding, stubFetch } from '@/test/fixtures'

const PROVIDERS = {
  mode: 'live',
  providers: [
    {
      name: 'nvidia',
      model: 'nemotron',
      external: true,
      state: 'closed',
      reopens_in_seconds: 0,
      reason: null,
    },
    {
      name: 'local',
      model: 'qwen3',
      external: false,
      state: 'closed',
      reopens_in_seconds: 0,
      reason: null,
    },
  ],
}

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  FakeEventSource.instances = []
  vi.stubGlobal('EventSource', FakeEventSource)
  window.matchMedia = vi
    .fn()
    .mockReturnValue({ matches: false }) as unknown as typeof window.matchMedia
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('upload page', () => {
  it('sends the file, depth and consent, then opens the scan', async () => {
    let sent: FormData | undefined
    vi.stubGlobal(
      'fetch',
      vi.fn(
        stubFetch({
          'GET /api/providers': () => PROVIDERS,
          'POST /api/scans': (init) => {
            sent = init?.body as FormData
            return { ...makeDetail().scan, status: 'queued' }
          },
          'GET /api/scans/scan1': () =>
            makeDetail({ scan: { ...makeDetail().scan, status: 'running' } }),
        }),
      ),
    )
    const user = userEvent.setup()
    renderAt('/')

    expect(await screen.findByText('nemotron')).toBeInTheDocument()
    await user.upload(
      screen.getByLabelText('Project file or archive'),
      new File(['x = 1\n'], 'app.py', { type: 'text/x-python' }),
    )
    await user.click(screen.getByLabelText(/Deep/))
    await user.click(screen.getByRole('checkbox', { name: /Send code excerpts/ }))
    await user.click(screen.getByRole('button', { name: 'Scan project' }))

    await waitFor(() => expect(sent).toBeDefined())
    expect(sent?.get('depth')).toBe('deep')
    expect(sent?.get('allow_external')).toBe('true')
    expect((sent?.get('file') as File).name).toBe('app.py')
    expect(await screen.findByRole('heading', { name: 'shop.zip' })).toBeInTheDocument()
  })

  it('explains that without consent only the local model reviews the code', async () => {
    vi.stubGlobal('fetch', vi.fn(stubFetch({ 'GET /api/providers': () => PROVIDERS })))
    renderAt('/')

    expect(
      await screen.findByText('Only a model on this machine will review your code.'),
    ).toBeInTheDocument()
  })
})

describe('scan page', () => {
  it('shows live progress, then the results with decisions', async () => {
    const finding = makeFinding({ rationale: 'An attacker controls name.' })
    let decision: string | undefined
    let status: ScanStatus = 'running'
    vi.stubGlobal(
      'fetch',
      vi.fn(
        stubFetch({
          'GET /api/scans/scan1': () => makeDetail({ scan: { ...makeDetail().scan, status } }),
          'GET /api/scans/scan1/findings': () => [finding],
          'GET /api/scans/scan1/files': () => ({
            files: [
              {
                path: 'app/db.py',
                language: 'python',
                lines: 5,
                findings: 1,
                highest_severity: 'high',
              },
            ],
            skipped: [],
          }),
          'GET /api/scans/scan1/files/app/db.py': () => ({
            path: 'app/db.py',
            language: 'python',
            content: 'import sqlite3\n\n\nquery = "SELECT * FROM users WHERE name = \'" + name\n',
          }),
          [`PATCH /api/scans/scan1/findings/${finding.id}`]: (init) => {
            decision = JSON.parse(init?.body as string).status
            return { ...finding, status: decision }
          },
        }),
      ),
    )
    const user = userEvent.setup()
    renderAt('/scans/scan1')

    const [source] = FakeEventSource.instances
    expect(source?.url).toBe('/api/scans/scan1/events')
    source?.emit({ kind: 'stage', stage: 'analyzing' })
    source?.emit({
      kind: 'tool',
      tool: 'bandit',
      state: 'ok',
      finding_count: 1,
      duration_ms: 40,
      message: null,
    })
    source?.emit({ kind: 'finding', finding })
    // The analyzer shows in its table and in the activity log.
    expect(await screen.findAllByText('bandit')).not.toHaveLength(0)
    expect(screen.getByText('SQL built with string concatenation')).toBeInTheDocument()

    status = 'done'
    source?.emit({ kind: 'status', status: 'done', message: null })

    expect(await screen.findByText('One injection needs fixing.')).toBeInTheDocument()
    expect(await screen.findByText('Why it matters:')).toBeInTheDocument()
    expect(screen.getByText('76')).toBeInTheDocument()
    expect(source?.closed).toBe(true)
    await user.click(screen.getByRole('button', { name: 'Reject' }))
    await waitFor(() => expect(decision).toBe('rejected'))
    expect(useScanStore.getState().status).toBe('done')
  })

  it('explains when a scan no longer exists', async () => {
    vi.stubGlobal('fetch', vi.fn(stubFetch({})))

    renderAt('/scans/expired')

    expect(await screen.findByRole('heading', { name: 'Scan not found' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Start a new scan' })).toHaveAttribute('href', '/')
  })
})
