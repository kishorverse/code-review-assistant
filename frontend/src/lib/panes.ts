/** A pane whose width the reviewer can drag, remembered between visits. */
import { useRef, useState, type KeyboardEvent, type PointerEvent } from 'react'

interface Options {
  /** localStorage key; the width is remembered per key. */
  key: string
  initial: number
  min: number
  max: number
  /** Which edge of the pane the handle sits on. Dragging a left edge leftwards widens it. */
  edge: 'left' | 'right'
}

const STEP = 24

function read(key: string): number | null {
  try {
    const value = Number(localStorage.getItem(key))
    return Number.isFinite(value) && value > 0 ? value : null
  } catch {
    return null
  }
}

function write(key: string, width: number): void {
  try {
    localStorage.setItem(key, String(width))
  } catch {
    // Not remembered; the width still applies to this page.
  }
}

export function useResizablePane({ key, initial, min, max, edge }: Options) {
  const clamp = (value: number) => Math.min(max, Math.max(min, Math.round(value)))
  const [width, setWidth] = useState(() => clamp(read(key) ?? initial))
  const [dragging, setDragging] = useState(false)
  // The width at any moment, for handlers; it only changes through `commit`.
  const latest = useRef(width)

  const commit = (value: number) => {
    const next = clamp(value)
    latest.current = next
    setWidth(next)
    return next
  }

  // Pointer capture keeps the drag alive when the pointer leaves the thin handle.
  const onPointerDown = (event: PointerEvent<HTMLElement>) => {
    if (event.button !== 0) return
    event.preventDefault()
    const handle = event.currentTarget
    handle.setPointerCapture(event.pointerId)
    const startX = event.clientX
    const startWidth = latest.current
    setDragging(true)
    document.body.style.cursor = 'col-resize'
    document.body.style.userSelect = 'none'

    const move = (moveEvent: globalThis.PointerEvent) => {
      const delta = moveEvent.clientX - startX
      commit(startWidth + (edge === 'left' ? -delta : delta))
    }
    const end = () => {
      handle.removeEventListener('pointermove', move)
      handle.removeEventListener('pointerup', end)
      handle.removeEventListener('pointercancel', end)
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
      setDragging(false)
      write(key, latest.current)
    }
    handle.addEventListener('pointermove', move)
    handle.addEventListener('pointerup', end)
    handle.addEventListener('pointercancel', end)
  }

  // Arrow keys resize too, so the handle works without a pointer.
  const onKeyDown = (event: KeyboardEvent<HTMLElement>) => {
    if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return
    event.preventDefault()
    const grow = (event.key === 'ArrowLeft') === (edge === 'left')
    write(key, commit(latest.current + (grow ? STEP : -STEP)))
  }

  const reset = () => write(key, commit(initial))

  return {
    width,
    dragging,
    handleProps: {
      role: 'separator' as const,
      'aria-orientation': 'vertical' as const,
      'aria-valuemin': min,
      'aria-valuemax': max,
      'aria-valuenow': width,
      tabIndex: 0,
      onPointerDown,
      onKeyDown,
      onDoubleClick: reset,
    },
  }
}
