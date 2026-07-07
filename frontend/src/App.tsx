import { QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter, Link, Route, Routes } from 'react-router-dom'

import companyLogo from '../assets/gradient-company-logo-cn.png'

import { Layout } from './components/Layout'
import { AccountPage } from './features/account/AccountPage'
import { LoginPage } from './features/auth/LoginPage'
import { ProtectedRoute } from './features/auth/ProtectedRoute'
import { RegisterPage } from './features/auth/RegisterPage'
import { SessionProvider } from './features/auth/SessionProvider'
import { GuestCalculatorPage } from './features/calculator/GuestCalculatorPage'
import { CourseDetailPage } from './features/courses/CourseDetailPage'
import { DashboardPage } from './features/dashboard/DashboardPage'
import { HistoryPage } from './features/history/HistoryPage'
import { ImportPage } from './features/import/ImportPage'
import { PlannerPage } from './features/planner/PlannerPage'
import { RecommendationsPage } from './features/recommendations/RecommendationsPage'
import { SearchPage } from './features/search/SearchPage'
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
                <Route path="/dashboard" element={<DashboardPage />} />
                <Route path="/courses/:enrolmentId" element={<CourseDetailPage />} />
                <Route path="/history" element={<HistoryPage />} />
                <Route path="/planner" element={<PlannerPage />} />
                <Route path="/import" element={<ImportPage />} />
                <Route path="/recommendations" element={<RecommendationsPage />} />
                <Route path="/study-plans" element={<StudyPlanPage />} />
                <Route path="/search" element={<SearchPage />} />
                <Route path="/account" element={<AccountPage />} />
              </Route>
            </Route>
          </Routes>
        </BrowserRouter>
      </SessionProvider>
    </QueryClientProvider>
  )
}
