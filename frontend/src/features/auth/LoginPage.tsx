import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { useSession } from './SessionProvider'

export function LoginPage() {
  const { signIn } = useSession()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setIsSubmitting(true)
    setError(null)
    const failure = await signIn(email, password)
    setIsSubmitting(false)
    if (failure) {
      setError(failure)
      return
    }
    navigate('/dashboard')
  }

  return (
    <main className="auth-page">
      <h1>Log in to Gradient</h1>
      <form onSubmit={handleSubmit} className="stacked-form">
        <label>
          Email
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            autoComplete="email"
          />
        </label>
        <label>
          Password
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            autoComplete="current-password"
          />
        </label>
        {error && <p role="alert" className="form-error">{error}</p>}
        <button type="submit" disabled={isSubmitting}>
          {isSubmitting ? 'Logging in…' : 'Log in'}
        </button>
      </form>
      <p>
        New here? <Link to="/register">Create an account</Link> or{' '}
        <Link to="/calculator">try the calculator without one</Link>.
      </p>
    </main>
  )
}
