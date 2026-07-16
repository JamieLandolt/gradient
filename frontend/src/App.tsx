import { QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter, Link, Route, Routes } from 'react-router-dom'

import companyLogo from '../assets/gradient-company-logo-cn.png'

import { ErrorBoundary } from './components/ErrorBoundary'
import { Layout } from './components/Layout'
import { AccountPage } from './features/account/AccountPage'
import { AssistantPage } from './features/assistant/AssistantPage'
import { LoginPage } from './features/auth/LoginPage'
import { ProtectedRoute } from './features/auth/ProtectedRoute'
import { RegisterPage } from './features/auth/RegisterPage'
import { SessionProvider } from './features/auth/SessionProvider'
import { GuestCalculatorPage } from './features/calculator/GuestCalculatorPage'
import { CourseDetailPage } from './features/courses/CourseDetailPage'
import { DashboardPage } from './features/dashboard/DashboardPage'
import { DiscoverPage } from './features/discover/DiscoverPage'
import { HistoryPage } from './features/history/HistoryPage'
import { ImportPage } from './features/import/ImportPage'
import { PlannerPage } from './features/planner/PlannerPage'
import { StudyPlanPage } from './features/study-plans/StudyPlanPage'
import { createQueryClient } from './lib/queryClient'

const queryClient = createQueryClient()

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
                <Route path="/study-plans" element={<StudyPlanPage />} />
                <Route path="/assistant" element={<AssistantPage />} />
                <Route path="/discover" element={<DiscoverPage />} />
                <Route path="/account" element={<AccountPage />} />
              </Route>
            </Route>
          </Routes>
          </ErrorBoundary>
        </BrowserRouter>
      </SessionProvider>
    </QueryClientProvider>
  )
}
