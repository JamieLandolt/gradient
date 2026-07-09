import { Link, NavLink, Outlet } from 'react-router-dom'

import appIcon from '../../assets/gradient-app-icon.png'
import { useSession } from '../features/auth/SessionProvider'

export function DisclaimerBanner() {
  return (
    <p role="note" className="disclaimer">
      Gradient's figures are estimates to support your own decisions — your course profile
      (ECP) and official university records remain authoritative.
    </p>
  )
}

export function Layout() {
  const { session, signOut } = useSession()

  return (
    <div className="app-shell">
      <header className="app-header">
        <Link to="/" className="brand">
          <img src={appIcon} alt="" className="brand-logo" />
          Gradient
        </Link>
        <nav aria-label="Main">
          {session ? (
            <>
              <NavLink to="/dashboard">Dashboard</NavLink>
              <NavLink to="/history">History</NavLink>
              <NavLink to="/planner">Planner</NavLink>
              <NavLink to="/recommendations">Recommendations</NavLink>
              <NavLink to="/assistant">Assistant</NavLink>
              <NavLink to="/search">Search</NavLink>
              <NavLink to="/import">Import</NavLink>
              <NavLink to="/account">Account</NavLink>
              <button type="button" className="link-button" onClick={() => void signOut()}>
                Log out
              </button>
            </>
          ) : (
            <>
              <NavLink to="/calculator">Calculator</NavLink>
              <NavLink to="/login">Log in</NavLink>
              <NavLink to="/register">Register</NavLink>
            </>
          )}
        </nav>
      </header>
      <DisclaimerBanner />
      <div className="app-content">
        <Outlet />
      </div>
    </div>
  )
}
