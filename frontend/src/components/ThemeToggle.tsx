import { Moon, Sun } from 'lucide-react'
import { useEffect, useState } from 'react'

const STORAGE_KEY = 'margin-theme'

/** Light and dark, following the system setting until the reviewer picks one. */
export function ThemeToggle() {
  const [dark, setDark] = useState(() => {
    const stored = readChoice()
    if (stored) return stored === 'dark'
    return window.matchMedia('(prefers-color-scheme: dark)').matches
  })

  useEffect(() => {
    document.documentElement.classList.toggle('dark', dark)
  }, [dark])

  const toggle = () => {
    setDark(!dark)
    rememberChoice(!dark)
  }

  return (
    <button
      type="button"
      onClick={toggle}
      className="rounded-control border-line hover:border-brand inline-flex items-center gap-1 border px-2 py-1 text-[13px]"
      aria-pressed={dark}
    >
      {dark ? <Moon aria-hidden className="size-3.5" /> : <Sun aria-hidden className="size-3.5" />}
      {dark ? 'Dark' : 'Light'}
    </button>
  )
}

// Storage can be blocked (private windows, strict settings); the theme then simply isn't remembered.
function readChoice(): string | null {
  try {
    return localStorage.getItem(STORAGE_KEY)
  } catch {
    return null
  }
}

function rememberChoice(dark: boolean): void {
  try {
    localStorage.setItem(STORAGE_KEY, dark ? 'dark' : 'light')
  } catch {
    // Not remembered; the choice still applies to this page.
  }
}
