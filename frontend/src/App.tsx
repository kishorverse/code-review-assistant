import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Link, Route, Routes } from 'react-router'
import { Toaster } from 'sonner'

import { ThemeToggle } from '@/components/ThemeToggle'
import { ScanPage } from '@/features/scan/ScanPage'
import { UploadPage } from '@/features/upload/UploadPage'

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
})

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <div className="min-h-svh">
        <header className="border-line flex items-center gap-4 border-b px-4 py-2">
          <Link to="/" className="font-display text-[18px]">
            Margin
          </Link>
          <nav className="text-muted ml-auto flex items-center gap-3 text-[13px]">
            <a
              href="https://github.com/kishorverse/code-review-assistant"
              className="hover:text-text"
            >
              GitHub
            </a>
            <ThemeToggle />
          </nav>
        </header>
        <Routes>
          <Route path="/" element={<UploadPage />} />
          <Route path="/scans/:scanId" element={<ScanPage />} />
          <Route
            path="*"
            element={
              <p className="p-6">
                Nothing here.{' '}
                <Link to="/" className="text-brand underline">
                  Start a scan
                </Link>
                .
              </p>
            }
          />
        </Routes>
        <Toaster position="bottom-right" />
      </div>
    </QueryClientProvider>
  )
}

export default App
