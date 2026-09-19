import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Compass } from 'lucide-react'
import { Link, Route, Routes, useLocation } from 'react-router'
import { Toaster } from 'sonner'

import { AppShell } from '@/components/AppShell'
import { ScanPage } from '@/features/scan/ScanPage'
import { UploadPage } from '@/features/upload/UploadPage'

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
})

function App() {
  const location = useLocation()
  return (
    <QueryClientProvider client={queryClient}>
      <AppShell>
        {/* Keyed by path, so every page enters with the same soft rise. */}
        <div key={location.pathname} className="page-enter h-full">
          <Routes location={location}>
            <Route path="/" element={<UploadPage />} />
            <Route path="/scans/:scanId" element={<ScanPage />} />
            <Route path="*" element={<NotFound />} />
          </Routes>
        </div>
      </AppShell>
      <Toaster
        position="bottom-right"
        toastOptions={{
          className:
            '!rounded-[12px] !border-line !bg-elevated !text-text !text-[13px] !shadow-lift !font-sans',
        }}
      />
    </QueryClientProvider>
  )
}

function NotFound() {
  return (
    <div className="mx-auto max-w-lg px-6 py-28 text-center">
      <span className="border-line bg-surface shadow-panel mx-auto grid size-12 place-items-center rounded-2xl border">
        <Compass aria-hidden className="text-faint size-5" />
      </span>
      <h1 className="display mt-6 text-[40px] leading-none">Page not found</h1>
      <p className="text-muted mt-3 text-[13.5px]">There is nothing at this address.</p>
      <Link
        to="/"
        className="text-accent-text mt-6 inline-block text-[13.5px] font-medium hover:underline"
      >
        Start a new review
      </Link>
    </div>
  )
}

export default App
