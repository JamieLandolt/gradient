import { QueryClientProvider } from '@tanstack/react-query'
import { Suspense, lazy, Component } from 'react'
import type { ErrorInfo, ReactNode } from 'react'
import { BrowserRouter, Link, Route, Routes } from 'react-router-dom'

import companyLogo from '../assets/gradient-company-logo-cn.png'

import { Layout } from './components/Layout'
import { ProtectedRoute } from './features/auth/ProtectedRoute'
import { SessionProvider } from './features/auth/SessionProvider'
import { createQueryClient } from './lib/queryClient'

const AccountPage = lazy(() => import('./features/account/AccountPage').then(m => ({ default: m.AccountPage })))
const AssistantPage = lazy(() => import('./features/assistant/AssistantPage').then(m => ({ default: m.AssistantPage })))
const LoginPage = lazy(() => import('./features/auth/LoginPage').then(m => ({ default: m.LoginPage })))
const RegisterPage = lazy(() => import('./features/auth/RegisterPage').then(m => ({ default: m.RegisterPage })))
const GuestCalculatorPage = lazy(() => import('./features/calculator/GuestCalculatorPage').then(m => ({ default: m.GuestCalculatorPage })))
const CourseDetailPage = lazy(() => import('./features/courses/CourseDetailPage').then(m => ({ default: m.CourseDetailPage })))
const DashboardPage = lazy(() => import('./features/dashboard/DashboardPage').then(m => ({ default: m.DashboardPage })))
const HistoryPage = lazy(() => import('./features/history/HistoryPage').then(m => ({ default: m.HistoryPage })))
const ImportPage = lazy(() => import('./features/import/ImportPage').then(m => ({ default: m.ImportPage })))
const PlannerPage = lazy(() => import('./features/planner/PlannerPage').then(m => ({ default: m.PlannerPage })))
const RecommendationsPage = lazy(() => import('./features/recommendations/RecommendationsPage').then(m => ({ default: m.RecommendationsPage })))
const SearchPage = lazy(() => import('./features/search/SearchPage').then(m => ({ default: m.SearchPage })))
const StudyPlanPage = lazy(() => import('./features/study-plans/StudyPlanPage').then(m => ({ default: m.StudyPlanPage })))

const queryClient = createQueryClient()

function LoadingFallback() {
  return (
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '40vh' }}>
      <p>Loading…</p>
    </div>
  )
}

function NotFoundPage() {
  return (
    <main style={{ textAlign: 'center', padding: '4rem 1rem' }}>
      <h1>404 — Page not found</h1>
      <p>The page you are looking for does not exist.</p>
      <Link to="/" className="btn btn-primary">Go home</Link>
    </main>
  )
}

interface ErrorBoundaryState {
  hasError: boolean
}

class ErrorBoundary extends Component<{ children: ReactNode }, ErrorBoundaryState> {
  state: ErrorBoundaryState = { hasError: false }

  static getDerivedStateFromError(): ErrorBoundaryState {
    return { hasError: true }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Uncaught error:', error, info)
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{ textAlign: 'center', padding: '4rem 1rem' }}>
          <h1>Something went wrong</h1>
          <p>An unexpected error occurred.</p>
          <button className="btn btn-primary" onClick={() => window.location.reload()}>
            Reload page
          </button>
        </div>
      )
    }
    return this.props.children
  }
}

function HomePage() {
  return (
    <main className="home-hero">
      <h1>
        <span className="brand-plate">
          <img src={companyLogo} alt="Gradient" className="home-logo" />
        </span>
      </h1>
      <p className="home-tagline">
        Track your marks, see exactly what you need on remaining assessment to hit your
        target grade, and plan your degree around prerequisites.
      </p>
      <div className="cta-row">
        <Link to="/register" className="btn btn-primary">
          Create an account
        </Link>
        <Link to="/login" className="btn btn-outline">
          Log in
        </Link>
        <Link to="/calculator" className="btn btn-outline">
          Try the calculator
        </Link>
      </div>
      <p className="cta-note">The target-grade calculator works without an account.</p>
    </main>
  )
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <SessionProvider>
        <BrowserRouter>
          <ErrorBoundary>
            <Suspense fallback={<LoadingFallback />}>
              <Routes>
                <Route element={<Layout />}>
                  <Route path="/" element={<HomePage />} />
                  <Route path="/calculator" element={<GuestCalculatorPage />} />
                  <Route path="/login" element={<LoginPage />} />
                  <Route path="/register" element={<RegisterPage />} />
                  <Route element={<ProtectedRoute />}>
                    <Route path="/dashboard" element={<DashboardPage />} />
                    <Route path="/courses/:enrolmentId" element={<CourseDetailPage />} />
                    <Route path="/history" element={<HistoryPage />} />
                    <Route path="/planner" element={<PlannerPage />} />
                    <Route path="/import" element={<ImportPage />} />
                    <Route path="/recommendations" element={<RecommendationsPage />} />
                    <Route path="/study-plans" element={<StudyPlanPage />} />
                    <Route path="/assistant" element={<AssistantPage />} />
                    <Route path="/search" element={<SearchPage />} />
                    <Route path="/account" element={<AccountPage />} />
                  </Route>
                  <Route path="*" element={<NotFoundPage />} />
                </Route>
              </Routes>
            </Suspense>
          </ErrorBoundary>
        </BrowserRouter>
      </SessionProvider>
    </QueryClientProvider>
  )
}
