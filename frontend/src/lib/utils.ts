import type { CSSProperties } from 'react'

export { cn } from 'cn'

/** Staggers an entrance animation: the nth item starts a beat after the one before it. */
export const stagger = (index: number) => ({ '--i': index }) as CSSProperties
