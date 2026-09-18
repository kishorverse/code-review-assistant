import type { CallRecord, Finding, ScanDetail } from '@/lib/api'

export function makeFinding(overrides: Partial<Finding> = {}): Finding {
  return {
    id: 'f1',
    file_path: 'app/db.py',
    start_line: 4,
    end_line: 4,
    start_column: null,
    end_column: null,
    category: 'security',
    severity: 'high',
    title: 'SQL built with string concatenation',
    message: 'User input reaches the query.',
    rationale: null,
    evidence: 'query = "SELECT * FROM users WHERE name = \'" + name',
    rule_id: 'B608',
    sources: ['bandit'],
    confidence: 1,
    status: 'open',
    cwe: 'CWE-89',
    suggestion: null,
    verified_by: [],
    ai_note: null,
    ...overrides,
  }
}

export function makeCall(overrides: Partial<CallRecord> = {}): CallRecord {
  return {
    task: 'review',
    provider: 'nvidia',
    model: 'nemotron',
    status: 'ok',
    latency_ms: 1200,
    input_tokens: 300,
    output_tokens: 80,
    detail: null,
    file_path: 'app/db.py',
    ...overrides,
  }
}

export function makeDetail(overrides: Partial<ScanDetail> = {}): ScanDetail {
  return {
    scan: {
      id: 'scan1',
      source: 'shop.zip',
      status: 'done',
      depth: 'standard',
      allow_external: true,
      created_at: '2026-09-18T08:00:00Z',
      started_at: '2026-09-18T08:00:01Z',
      finished_at: '2026-09-18T08:00:30Z',
      error: null,
    },
    summary: null,
    score: {
      score: 76,
      grade: 'B',
      kloc: 0.03,
      finding_penalty: 14,
      complexity_penalty: 10,
      functions: 2,
      complex_functions: 1,
      formula: '100 - findings - complexity',
    },
    ai_summary: {
      headline: 'One injection needs fixing.',
      strengths: [],
      top_risks: [],
      recommended_next_steps: ['Parameterize the query.'],
    },
    calls: [makeCall()],
    ...overrides,
  }
}

/** A `fetch` stub answering by method and path. */
export function stubFetch(
  routes: Record<string, (init?: RequestInit) => unknown>,
): (input: RequestInfo | URL, init?: RequestInit) => Promise<Response> {
  return async (input, init) => {
    const url = typeof input === 'string' ? input : input.toString()
    const key = `${init?.method ?? 'GET'} ${url}`
    const handler = routes[key]
    if (!handler)
      return new Response(JSON.stringify({ detail: `no stub for ${key}` }), { status: 404 })
    return new Response(JSON.stringify(handler(init)), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    })
  }
}

/** A minimal EventSource that tests drive by hand. */
export class FakeEventSource {
  static instances: FakeEventSource[] = []
  readonly url: string
  closed = false
  private listeners = new Map<string, ((event: MessageEvent<string>) => void)[]>()

  constructor(url: string) {
    this.url = url
    FakeEventSource.instances.push(this)
  }

  addEventListener(kind: string, listener: (event: MessageEvent<string>) => void): void {
    this.listeners.set(kind, [...(this.listeners.get(kind) ?? []), listener])
  }

  close(): void {
    this.closed = true
  }

  emit(payload: { kind: string } & Record<string, unknown>): void {
    const event = new MessageEvent<string>(payload.kind, { data: JSON.stringify(payload) })
    for (const listener of this.listeners.get(payload.kind) ?? []) listener(event)
  }
}
