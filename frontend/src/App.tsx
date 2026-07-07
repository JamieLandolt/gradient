import { QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter, Route, Routes } from 'react-router-dom'

import { createQueryClient } from './lib/queryClient'

const queryClient = createQueryClient()

function HomePage() {
  return (
    <main>
      <h1>Gradient</h1>
      <p>Grade tracking &amp; degree planning for UQ students.</p>
      <p role="note">
        Gradient&apos;s figures are estimates to support your own decisions — your course
        profile (ECP) and official university records remain authoritative.
      </p>
    </main>
  )
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<HomePage />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
