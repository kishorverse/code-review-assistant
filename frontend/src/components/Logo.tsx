/**
 * Margin's mark: a monogram "M" on a solid ink tile. Flat and monochrome by
 * design — it inverts automatically between themes instead of carrying its
 * own colours, the way a wordmark on letterhead would.
 */
export function Logo({ className = 'size-7' }: { className?: string }) {
  return (
    <svg viewBox="0 0 28 28" fill="none" aria-hidden className={className}>
      <rect width="28" height="28" rx="7" className="fill-text" />
      <path
        d="M8 19V9.4c0-.5.53-.82.97-.58L14 11.6l5.03-2.78c.44-.24.97.08.97.58V19"
        className="stroke-canvas"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}
