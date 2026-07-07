import { QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter, Link, Route, Routes } from 'react-router-dom'

import { Layout } from './components/Layout'
import { LoginPage } from './features/auth/LoginPage'
import { ProtectedRoute } from './features/auth/ProtectedRoute'
import { RegisterPage } from './features/auth/RegisterPage'
import { SessionProvider } from './features/auth/SessionProvider'
import { GuestCalculatorPage } from './features/calculator/GuestCalculatorPage'
import { createQueryClient } from './lib/queryClient'

const queryClient = createQueryClient()

function HomePage() {
  return (
    <main>
      <h1>Gradient</h1>
      <p>
        Track your marks, see exactly what you need on remaining assessment to hit your
        target grade, and plan your degree around prerequisites.
      </p>
      <p>
        <Link to="/register">Create an account</Link>,{' '}
        <Link to="/login">log in</Link>, or{' '}
        <Link to="/calculator">try the target-grade calculator</Link> without one.
      </p>
    </main>
  )
}

function DashboardPlaceholder() {
  return (
    <main>
      <h1>Dashboard</h1>
      <p className="page-status">Your courses will appear here.</p>
    </main>
  )
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <SessionProvider>
        <BrowserRouter>
          <Routes>
            <Route element={<Layout />}>
              <Route path="/" element={<HomePage />} />
              <Route path="/calculator" element={<GuestCalculatorPage />} />
              <Route path="/login" element={<LoginPage />} />
              <Route path="/register" element={<RegisterPage />} />
              <Route element={<ProtectedRoute />}>
                <Route path="/dashboard" element={<DashboardPlaceholder />} />
              </Route>
            </Route>
          </Routes>
        </BrowserRouter>
      </SessionProvider>
    </QueryClientProvider>
  )
}
