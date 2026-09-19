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
  instant = false,
): void {
  // A jump to another file should land at once; a smooth scroll from line 1 reads as lag.
  const previous = container.style.scrollBehavior
  if (instant) container.style.scrollBehavior = 'auto'
  scrollTo(container, element, align)
  if (instant) container.style.scrollBehavior = previous
}

function scrollTo(container: HTMLElement, element: HTMLElement, align: 'center' | 'nearest'): void {
  const view = container.getBoundingClientRect()
  const box = element.getBoundingClientRect()
  const top = box.top - view.top + container.scrollTop
  if (align === 'center') {
    container.scrollTop = top - (container.clientHeight - box.height) / 2
  } else if (box.top < view.top || box.height > container.clientHeight) {
    // Too tall to fit: show its start, where the title is, rather than its end.
    container.scrollTop = top
  } else if (box.bottom > view.bottom) {
    container.scrollTop = top + box.height - container.clientHeight
  }
}
