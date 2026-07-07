import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { useSession } from './SessionProvider'

const MIN_PASSWORD_LENGTH = 8

export function RegisterPage() {
  const { signUp } = useSession()
  const navigate = useNavigate()
  const [displayName, setDisplayName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (password.length < MIN_PASSWORD_LENGTH) {
      setError(`Password must be at least ${MIN_PASSWORD_LENGTH} characters`)
      return
    }
    setIsSubmitting(true)
    setError(null)
    const failure = await signUp(email, password, displayName)
    setIsSubmitting(false)
    if (failure) {
      setError(failure)
      return
    }
    navigate('/dashboard')
  }

  return (
    <main className="auth-page">
      <h1>Create your Gradient account</h1>
      <form onSubmit={handleSubmit} className="stacked-form">
        <label>
          Display name
          <input
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            required
            autoComplete="name"
          />
        </label>
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
            autoComplete="new-password"
          />
        </label>
        {error && <p role="alert" className="form-error">{error}</p>}
        <button type="submit" disabled={isSubmitting}>
          {isSubmitting ? 'Creating account…' : 'Register'}
        </button>
      </form>
      <p>
        Already registered? <Link to="/login">Log in</Link>.
      </p>
    </main>
  )
}
