import {
  ArrowUpRight,
  BookOpen,
  ChevronsLeft,
  ChevronsRight,
  FileArchive,
  FolderGit2,
  Plus,
} from 'lucide-react'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { Link, NavLink, useNavigate } from 'react-router'

import { Logo } from '@/components/Logo'
import { ThemeToggle } from '@/components/ThemeToggle'
import { timeAgo, useRecentScans } from '@/lib/recent'
import {
  setSidebarCollapsed,
  setSidebarWidth,
  SIDEBAR_COLLAPSED_WIDTH,
  SIDEBAR_MAX,
  SIDEBAR_MIN,
  useSidebarCollapsed,
  useSidebarWidth,
} from '@/lib/sidebar'
import { stagger } from '@/lib/utils'

const REPOSITORY = 'https://github.com/kishorverse/code-review-assistant'

/** The application frame: navigation on the left, the page on the right. */
export function AppShell({ children }: { children: ReactNode }) {
  useNewReviewShortcut()
  return (
    <div className="flex h-full min-h-0 flex-col md:flex-row">
      <Sidebar />
      <MobileBar />
      <main className="relative min-w-0 flex-1 overflow-y-auto">{children}</main>
    </div>
  )
}

/** n starts a new review from anywhere, unless the reviewer is typing. */
function useNewReviewShortcut(): void {
  const navigate = useNavigate()
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== 'n' || event.metaKey || event.ctrlKey || event.altKey) return
      if (event.target instanceof HTMLElement && event.target.closest('input, select, textarea')) {
        return
      }
      void navigate('/')
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [navigate])
}

function Brand({ collapsed }: { collapsed: boolean }) {
  return (
    <Link
      to="/"
      className={`group flex items-center gap-2.5 overflow-hidden px-1 ${collapsed ? 'justify-center' : ''}`}
    >
      <Logo className="size-7 shrink-0 transition-transform duration-500 ease-spring group-hover:scale-105" />
      {!collapsed && (
        <span className="fade-in flex min-w-0 flex-col leading-none">
          <span className="truncate text-[15px] font-semibold tracking-tight">Margin</span>
          <span className="text-faint mt-1 truncate text-[10.5px] font-medium tracking-wide">
            AI code review
          </span>
        </span>
      )}
    </Link>
  )
}

const navItem = (isActive: boolean, collapsed: boolean) =>
  `group rounded-control relative flex items-center gap-2 transition-all duration-200 ${
    collapsed ? 'justify-center px-0' : 'px-2'
  } ${
    isActive
      ? 'bg-surface text-text shadow-[0_0_0_1px_var(--color-line),0_1px_2px_rgb(0_0_0/0.05)]'
      : 'text-muted hover:bg-hover hover:text-text'
  }`

function Sidebar() {
  const recent = useRecentScans()
  const width = useSidebarWidth()
  const collapsed = useSidebarCollapsed()
  const dragging = useResizableSidebar()
  const effectiveWidth = collapsed ? SIDEBAR_COLLAPSED_WIDTH : width

  return (
    <aside
      style={{ width: effectiveWidth }}
      className={`border-line bg-canvas relative hidden min-w-0 shrink-0 flex-col border-r md:flex ${
        dragging ? '' : 'transition-[width] duration-300 ease-out-expo'
      }`}
    >
      <div className="flex h-16 shrink-0 items-center px-4">
        <Brand collapsed={collapsed} />
      </div>
      <div className={collapsed ? 'px-2.5' : 'px-3'}>
        <NavLink
          to="/"
          end
          title="New review (N)"
          className={({ isActive }) =>
            `${navItem(isActive, collapsed)} h-9 text-[13px] font-medium`
          }
        >
          <span className="bg-accent/10 text-accent-text grid size-5 shrink-0 place-items-center rounded-md transition-transform duration-300 group-hover:rotate-90">
            <Plus aria-hidden className="size-3.5" strokeWidth={2.25} />
          </span>
          {!collapsed && (
            <>
              <span className="fade-in min-w-0 flex-1 truncate">New review</span>
              <kbd
                aria-hidden
                className="border-line text-faint bg-surface fade-in ml-auto rounded border px-1 font-sans text-[10.5px]"
              >
                N
              </kbd>
            </>
          )}
        </NavLink>
      </div>

      {!collapsed && (
        <nav
          aria-label="Recent reviews"
          className="fade-in mt-7 min-h-0 flex-1 overflow-y-auto px-3"
        >
          <p className="eyebrow px-2 pb-2">Recent</p>
          {recent.length === 0 ? (
            <div className="border-line text-faint mx-1 rounded-[10px] border border-dashed px-3 py-4 text-[12.5px] leading-relaxed">
              Reviews you start appear here, so you can come back to them.
            </div>
          ) : (
            <ul className="space-y-0.5">
              {recent.map((scan, index) => (
                <li key={scan.id} className="rise" style={stagger(index)}>
                  <NavLink
                    to={`/scans/${scan.id}`}
                    className={({ isActive }) => `${navItem(isActive, false)} py-1.5`}
                  >
                    {({ isActive }) => (
                      <>
                        <span
                          aria-hidden
                          className={`bg-accent absolute top-1/2 -left-3 h-4 w-[3px] -translate-y-1/2 rounded-r-full transition-all duration-300 ${
                            isActive ? 'opacity-100' : 'scale-y-0 opacity-0'
                          }`}
                        />
                        <FileArchive
                          aria-hidden
                          className={`size-4 shrink-0 transition-colors ${isActive ? 'text-accent-text' : 'opacity-60'}`}
                        />
                        <span className="min-w-0 flex-1 truncate text-[13px]">{scan.source}</span>
                        <span className="text-faint shrink-0 text-[11px] tabular-nums">
                          {timeAgo(scan.createdAt)}
                        </span>
                      </>
                    )}
                  </NavLink>
                </li>
              ))}
            </ul>
          )}
        </nav>
      )}
      {collapsed && <div className="flex-1" />}

      <div
        className={`border-line space-y-0.5 border-t p-3 ${collapsed ? 'flex flex-col items-center px-2.5' : ''}`}
      >
        <ExternalLink href={`${REPOSITORY}/tree/main/docs`} icon={BookOpen} collapsed={collapsed}>
          Documentation
        </ExternalLink>
        <ExternalLink href={REPOSITORY} icon={FolderGit2} collapsed={collapsed}>
          Source
        </ExternalLink>
        <ThemeToggle compact={collapsed} />
      </div>

      <ResizeHandle collapsed={collapsed} />
    </aside>
  )
}

/** The hairline at the sidebar's edge: drag to resize, or click the button to collapse. */
function ResizeHandle({ collapsed }: { collapsed: boolean }) {
  return (
    <div
      className="group absolute inset-y-0 -right-2.5 z-10 flex w-5 cursor-col-resize items-center justify-center"
      data-sidebar-handle
    >
      <span className="group-hover:bg-accent/50 h-full w-px bg-transparent transition-colors duration-200" />
      <button
        type="button"
        title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        onClick={(event) => {
          event.stopPropagation()
          setSidebarCollapsed(!collapsed)
        }}
        className={`border-line bg-surface text-faint hover:text-accent-text hover:border-accent/40 absolute grid size-5 shrink-0 cursor-pointer place-items-center rounded-full border shadow-[0_1px_3px_rgb(0_0_0/0.12)] transition-all duration-200 ${
          collapsed
            ? 'scale-100 opacity-100'
            : 'scale-75 opacity-0 group-hover:scale-100 group-hover:opacity-100'
        }`}
      >
        {collapsed ? (
          <ChevronsRight aria-hidden className="size-3" />
        ) : (
          <ChevronsLeft aria-hidden className="size-3" />
        )}
      </button>
    </div>
  )
}

/** Drag anywhere on the handle (outside the button) to resize; returns whether it's live. */
function useResizableSidebar(): boolean {
  const [dragging, setDragging] = useState(false)
  const startRef = useRef({ x: 0, width: 0 })

  useEffect(() => {
    const handle = document.querySelector<HTMLElement>('[data-sidebar-handle]')
    if (!handle) return

    const onPointerDown = (event: PointerEvent) => {
      if ((event.target as HTMLElement).closest('button')) return
      startRef.current = { x: event.clientX, width: readCurrentWidth() }
      setDragging(true)
      document.body.style.userSelect = 'none'
      window.addEventListener('pointermove', onPointerMove)
      window.addEventListener('pointerup', onPointerUp, { once: true })
    }
    const onPointerMove = (event: PointerEvent) => {
      const delta = event.clientX - startRef.current.x
      setSidebarWidth(startRef.current.width + delta)
    }
    const onPointerUp = () => {
      setDragging(false)
      document.body.style.userSelect = ''
      window.removeEventListener('pointermove', onPointerMove)
    }

    handle.addEventListener('pointerdown', onPointerDown)
    return () => {
      handle.removeEventListener('pointerdown', onPointerDown)
      window.removeEventListener('pointermove', onPointerMove)
      document.body.style.userSelect = ''
    }
  }, [])

  return dragging
}

function readCurrentWidth(): number {
  const aside = document.querySelector('aside')
  return aside ? aside.getBoundingClientRect().width : (SIDEBAR_MIN + SIDEBAR_MAX) / 2
}

function ExternalLink({
  href,
  icon: Icon,
  collapsed,
  children,
}: {
  href: string
  icon: typeof BookOpen
  collapsed: boolean
  children: ReactNode
}) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      title={collapsed ? String(children) : undefined}
      className={`group rounded-control text-muted hover:bg-hover hover:text-text flex h-8 items-center gap-2 text-[13px] transition-colors ${
        collapsed ? 'w-8 justify-center' : 'w-full px-2'
      }`}
    >
      <Icon aria-hidden className="size-4 shrink-0" />
      {!collapsed && (
        <>
          <span className="fade-in min-w-0 flex-1 truncate">{children}</span>
          <ArrowUpRight
            aria-hidden
            className="ml-auto size-3.5 -translate-x-1 translate-y-1 opacity-0 transition-all duration-300 group-hover:translate-0 group-hover:opacity-60"
          />
        </>
      )}
    </a>
  )
}

function MobileBar() {
  return (
    <header className="border-line bg-surface/80 sticky top-0 z-20 flex h-14 items-center gap-2 border-b px-3 backdrop-blur-md md:hidden">
      <Brand collapsed={false} />
      <Link
        to="/"
        className="text-muted hover:text-text rounded-control hover:bg-hover ml-auto inline-flex h-8 items-center gap-1 px-2 text-[13px] transition-colors"
      >
        <Plus aria-hidden className="size-4" />
        New review
      </Link>
      <ThemeToggle compact />
    </header>
  )
}

/** A page's title row: where you are, what this is, and what you can do. */
export function PageHeader({
  crumbs,
  title,
  badge,
  meta,
  actions,
}: {
  crumbs?: { label: string; to?: string }[]
  title: string
  badge?: ReactNode
  meta?: ReactNode
  actions?: ReactNode
}) {
  return (
    <header className="border-line relative overflow-hidden border-b">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 bg-[radial-gradient(60%_120%_at_0%_0%,color-mix(in_srgb,var(--color-accent)_7%,transparent),transparent_70%)]"
      />
      <div className="bg-grid pointer-events-none absolute inset-0 opacity-60" aria-hidden />
      <div className="relative mx-auto flex max-w-[1600px] flex-wrap items-end gap-x-6 gap-y-3 px-6 pt-5 pb-4 lg:px-8">
        <div className="rise min-w-[min(100%,18rem)] flex-1 space-y-2">
          {crumbs && crumbs.length > 0 && (
            <nav
              aria-label="Breadcrumb"
              className="text-faint flex items-center gap-1.5 text-[12.5px]"
            >
              {crumbs.map((crumb, index) => (
                <span key={crumb.label} className="flex min-w-0 items-center gap-1.5">
                  {index > 0 && (
                    <span aria-hidden className="text-line-strong">
                      /
                    </span>
                  )}
                  {crumb.to ? (
                    <Link to={crumb.to} className="hover:text-text transition-colors">
                      {crumb.label}
                    </Link>
                  ) : (
                    <span className="truncate">{crumb.label}</span>
                  )}
                </span>
              ))}
            </nav>
          )}
          <div className="flex min-w-0 flex-wrap items-center gap-3">
            <h1 className="truncate text-[22px] leading-tight font-semibold tracking-[-0.02em]">
              {title}
            </h1>
            {badge}
          </div>
          {meta && <div className="text-muted text-[13px]">{meta}</div>}
        </div>
        {actions && (
          <div className="rise flex shrink-0 items-center gap-2" style={stagger(2)}>
            {actions}
          </div>
        )}
      </div>
    </header>
  )
}
