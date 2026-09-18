import { describe, expect, it } from 'vitest'

import { revealWithin } from '@/lib/scroll'

function pane(scrollTop: number): HTMLElement {
  const element = document.createElement('div')
  element.getBoundingClientRect = () => new DOMRect(0, 100, 300, 200)
  Object.defineProperty(element, 'clientHeight', { value: 200 })
  element.scrollTop = scrollTop
  return element
}

function row(top: number): HTMLElement {
  const element = document.createElement('div')
  element.getBoundingClientRect = () => new DOMRect(0, top, 300, 20)
  return element
}

describe('revealWithin', () => {
  it('centres the element in the pane', () => {
    const container = pane(0)

    revealWithin(container, row(500), 'center')

    expect(container.scrollTop).toBe(310)
  })

  it('scrolls just far enough for an element below or above the pane', () => {
    const below = pane(0)
    revealWithin(below, row(500), 'nearest')
    expect(below.scrollTop).toBe(220)

    const above = pane(100)
    revealWithin(above, row(50), 'nearest')
    expect(above.scrollTop).toBe(50)
  })

  it('leaves the pane alone when the element is already visible', () => {
    const container = pane(40)

    revealWithin(container, row(150), 'nearest')

    expect(container.scrollTop).toBe(40)
  })
})
