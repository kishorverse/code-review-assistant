/** Reviews started in this browser, for the sidebar.
 *
 * The API deliberately has no way to list scans: a scan id is the only key to
 * its results. So the browser remembers the reviews it started, and nothing more.
 * Storage can be unavailable (private windows, strict settings); the list is then
 * simply empty.
 */
import { useSyncExternalStore } from 'react'

export interface RecentScan {
  id: string
  source: string
  createdAt: string
}

const KEY = 'margin-recent-scans'
const LIMIT = 12
const CHANGED = 'margin-recent-changed'

let cache: RecentScan[] | null = null

function read(): RecentScan[] {
  if (cache) return cache
  try {
    const parsed: unknown = JSON.parse(localStorage.getItem(KEY) ?? '[]')
    cache = Array.isArray(parsed) ? (parsed as RecentScan[]) : []
  } catch {
    cache = []
  }
  return cache
}

/** Put a review at the top of the list. */
export function rememberScan(scan: RecentScan): void {
  cache = [scan, ...read().filter((entry) => entry.id !== scan.id)].slice(0, LIMIT)
  try {
    localStorage.setItem(KEY, JSON.stringify(cache))
  } catch {
    // Not remembered; the list still shows it for this session.
  }
  window.dispatchEvent(new Event(CHANGED))
}

/** Drop a review whose results no longer exist. */
export function forgetScan(id: string): void {
  if (!read().some((entry) => entry.id === id)) return
  cache = read().filter((entry) => entry.id !== id)
  try {
    localStorage.setItem(KEY, JSON.stringify(cache))
  } catch {
    // Nothing to do: the in-memory list is already updated.
  }
  window.dispatchEvent(new Event(CHANGED))
}

function subscribe(onChange: () => void): () => void {
  window.addEventListener(CHANGED, onChange)
  return () => window.removeEventListener(CHANGED, onChange)
}

export function useRecentScans(): RecentScan[] {
  return useSyncExternalStore(subscribe, read, () => [])
}

/** "3 min ago", "2 h ago", "18 Sep": short and stable enough for a sidebar. */
export function timeAgo(iso: string, now: Date = new Date()): string {
  const then = new Date(iso)
  const seconds = Math.max(0, (now.getTime() - then.getTime()) / 1000)
  if (seconds < 60) return 'just now'
  if (seconds < 3600) return `${Math.floor(seconds / 60)} min ago`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} h ago`
  return then.toLocaleDateString(undefined, { day: 'numeric', month: 'short' })
}
