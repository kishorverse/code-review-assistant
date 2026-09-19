/** The sidebar's width and collapsed state, persisted and shared across the app. */
import { useSyncExternalStore } from 'react'

const WIDTH_KEY = 'margin-sidebar-width'
const COLLAPSED_KEY = 'margin-sidebar-collapsed'
const CHANGED = 'margin-sidebar-changed'

export const SIDEBAR_MIN = 200
export const SIDEBAR_MAX = 360
export const SIDEBAR_DEFAULT = 232
export const SIDEBAR_COLLAPSED_WIDTH = 64

function clampWidth(width: number): number {
  return Math.min(SIDEBAR_MAX, Math.max(SIDEBAR_MIN, Math.round(width)))
}

function readWidth(): number {
  try {
    const stored = Number(localStorage.getItem(WIDTH_KEY))
    return Number.isFinite(stored) && stored > 0 ? clampWidth(stored) : SIDEBAR_DEFAULT
  } catch {
    return SIDEBAR_DEFAULT
  }
}

function readCollapsed(): boolean {
  try {
    return localStorage.getItem(COLLAPSED_KEY) === '1'
  } catch {
    return false
  }
}

export function setSidebarWidth(width: number): void {
  const clamped = clampWidth(width)
  try {
    localStorage.setItem(WIDTH_KEY, String(clamped))
  } catch {
    // Not remembered; the width still applies to this page.
  }
  window.dispatchEvent(new Event(CHANGED))
}

export function setSidebarCollapsed(collapsed: boolean): void {
  try {
    localStorage.setItem(COLLAPSED_KEY, collapsed ? '1' : '0')
  } catch {
    // Not remembered; the state still applies to this page.
  }
  window.dispatchEvent(new Event(CHANGED))
}

function subscribe(onChange: () => void): () => void {
  window.addEventListener(CHANGED, onChange)
  return () => window.removeEventListener(CHANGED, onChange)
}

export function useSidebarWidth(): number {
  return useSyncExternalStore(subscribe, readWidth, () => SIDEBAR_DEFAULT)
}

export function useSidebarCollapsed(): boolean {
  return useSyncExternalStore(subscribe, readCollapsed, () => false)
}
