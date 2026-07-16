import { useEffect, useState } from 'react'
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom'

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
  const location = useLocation()
  const [menuOpen, setMenuOpen] = useState(false)

  // Collapse the mobile menu whenever the route changes.
  useEffect(() => setMenuOpen(false), [location.pathname])

  return (
    <div className="app-shell">
      <header className="app-header">
        <Link to="/" className="brand">
          <img src={appIcon} alt="" className="brand-logo" />
          Gradient
        </Link>
        <button
          type="button"
          className="nav-toggle"
          aria-label="Toggle navigation"
          aria-expanded={menuOpen}
          aria-controls="main-nav"
          onClick={() => setMenuOpen((open) => !open)}
        >
          ☰
        </button>
        <nav id="main-nav" aria-label="Main" className={menuOpen ? 'nav-open' : undefined}>
          {session ? (
            <>
              <NavLink to="/dashboard">Dashboard</NavLink>
              <NavLink to="/history">History</NavLink>
              <NavLink to="/planner">Planner</NavLink>
              <NavLink to="/study-plans">Study plans</NavLink>
              <NavLink to="/assistant">Assistant</NavLink>
              <NavLink to="/discover">Discover</NavLink>
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
