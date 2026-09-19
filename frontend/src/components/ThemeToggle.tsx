import { Moon, Sun } from 'lucide-react'
import { useSyncExternalStore } from 'react'

const STORAGE_KEY = 'margin-theme'
const CHANGED = 'margin-theme-changed'

/** Light and dark, following the system setting until the reviewer picks one. */
export function ThemeToggle({ compact = false }: { compact?: boolean }) {
  // Every toggle on the page reads the same source: the class on <html>.
  const dark = useSyncExternalStore(subscribe, isDark)

  const toggle = () => {
    // Cross-fade colours for the switch itself, then get out of the way.
    const root = document.documentElement
    root.classList.add('theme-transition')
    window.setTimeout(() => root.classList.remove('theme-transition'), 360)
    root.classList.toggle('dark', !dark)
    rememberChoice(!dark)
    window.dispatchEvent(new Event(CHANGED))
  }

  return (
    <button
      type="button"
      onClick={toggle}
      aria-pressed={dark}
      title={dark ? 'Switch to light theme' : 'Switch to dark theme'}
      className={`text-muted hover:text-text group rounded-control inline-flex h-8 cursor-pointer items-center gap-2.5 text-[13px] transition-colors ${
        compact ? 'px-1' : 'hover:bg-hover w-full px-2'
      }`}
    >
      <span
        aria-hidden
        className="border-line bg-subtle relative inline-flex h-5 w-9 shrink-0 items-center rounded-full border"
      >
        <span
          className={`bg-surface text-text ease-spring absolute top-1/2 grid size-4 -translate-y-1/2 place-items-center rounded-full shadow-[0_1px_3px_rgb(0_0_0/0.2)] transition-[left] duration-500 ${
            dark ? 'left-[17px]' : 'left-[1px]'
          }`}
        >
          {dark ? <Moon className="size-2.5" /> : <Sun className="size-2.5" />}
        </span>
      </span>
      <span className={compact ? 'sr-only' : ''}>{dark ? 'Dark' : 'Light'} theme</span>
    </button>
  )
}

function isDark(): boolean {
  return document.documentElement.classList.contains('dark')
}

function subscribe(onChange: () => void): () => void {
  window.addEventListener(CHANGED, onChange)
  return () => window.removeEventListener(CHANGED, onChange)
}

function rememberChoice(dark: boolean): void {
  try {
    localStorage.setItem(STORAGE_KEY, dark ? 'dark' : 'light')
  } catch {
    // Storage can be blocked; the choice still applies to this page.
  }
}
