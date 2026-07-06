import { Navigate, Outlet } from 'react-router-dom'

import { useSession } from './SessionProvider'

export function ProtectedRoute() {
  const { session, isLoading } = useSession()

  if (isLoading) {
    return <p className="page-status">Loading your session…</p>
  }
  if (!session) {
    return <Navigate to="/login" replace />
  }
  return <Outlet />
}
