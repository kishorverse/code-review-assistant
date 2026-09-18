/**
 * Scroll `element` into view inside `container` alone.
 *
 * `scrollIntoView` also scrolls every scrollable ancestor, the page included, so selecting
 * a finding made the whole workspace jump. Setting `scrollTop` keeps the movement inside
 * the pane and still honours the pane's CSS `scroll-behavior`.
 */
export function revealWithin(
  container: HTMLElement,
  element: HTMLElement,
  align: 'center' | 'nearest',
): void {
  const view = container.getBoundingClientRect()
  const box = element.getBoundingClientRect()
  const top = box.top - view.top + container.scrollTop
  if (align === 'center') {
    container.scrollTop = top - (container.clientHeight - box.height) / 2
  } else if (box.top < view.top) {
    container.scrollTop = top
  } else if (box.bottom > view.bottom) {
    container.scrollTop = top + box.height - container.clientHeight
  }
}
