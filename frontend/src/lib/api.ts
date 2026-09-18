/** Typed access to the Margin API.
 *
 * Types come from `src/api/schema.d.ts`, generated from the backend's OpenAPI
 * document with `npm run api-types`, so the frontend cannot drift from the API.
 */
import type { components } from '@/api/schema'

type Schemas = components['schemas']

export type Finding = Schemas['Finding']
export type Severity = Schemas['Severity']
export type Category = Schemas['Category']
export type FindingStatus = Schemas['FindingStatus']
export type ScanInfo = Schemas['ScanInfo']
export type ScanDetail = Schemas['ScanDetail']
export type ScanStatus = Schemas['ScanStatus']
export type Depth = Schemas['Depth']
export type FileTree = Schemas['FileTree']
export type FileEntry = Schemas['FileEntry']
export type SkippedFile = Schemas['SkippedFile']
export type FileContent = Schemas['FileContent']
export type ProvidersView = Schemas['ProvidersView']
export type QualityScore = Schemas['QualityScore']
export type ReviewSummary = Schemas['ReviewSummary']
export type CallRecord = Schemas['CallRecord']
export type ReportFormat = 'json' | 'sarif' | 'html'
export type Decision = 'open' | 'accepted' | 'rejected'

export class ApiError extends Error {
  readonly status: number
  readonly reason: string | undefined

  constructor(status: number, message: string, reason?: string) {
    super(message)
    this.status = status
    this.reason = reason
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init)
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    const detail = typeof body.detail === 'string' ? body.detail : response.statusText
    throw new ApiError(response.status, detail, body.reason)
  }
  return response.status === 204 ? (undefined as T) : ((await response.json()) as T)
}

export async function createScan(input: {
  file: File
  depth: Depth
  allowExternal: boolean
}): Promise<ScanInfo> {
  const body = new FormData()
  body.append('file', input.file)
  body.append('depth', input.depth)
  body.append('allow_external', String(input.allowExternal))
  return request<ScanInfo>('/api/scans', { method: 'POST', body })
}

export const getScan = (id: string) => request<ScanDetail>(`/api/scans/${id}`)
export const listFindings = (id: string) => request<Finding[]>(`/api/scans/${id}/findings`)
export const getFiles = (id: string) => request<FileTree>(`/api/scans/${id}/files`)
export const getProviders = () => request<ProvidersView>('/api/providers')

export const getFile = (id: string, path: string) =>
  request<FileContent>(
    `/api/scans/${id}/files/${path.split('/').map(encodeURIComponent).join('/')}`,
  )

export const decideFinding = (id: string, findingId: string, status: Decision) =>
  request<Finding>(`/api/scans/${id}/findings/${findingId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status }),
  })

export const deleteScan = (id: string) => request<void>(`/api/scans/${id}`, { method: 'DELETE' })

export const reportUrl = (id: string, format: ReportFormat) =>
  `/api/scans/${id}/report?format=${format}`

export const eventsUrl = (id: string) => `/api/scans/${id}/events`
