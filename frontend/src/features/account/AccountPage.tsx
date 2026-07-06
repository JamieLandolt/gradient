import { useMutation, useQuery } from '@tanstack/react-query'
import { useState } from 'react'

import { ApiError, apiClient } from '../../lib/apiClient'
import { useSession } from '../auth/SessionProvider'
import type { UserProgramLink } from '../../types/api'

interface Profile {
  id: string
  display_name: string
  role: string
  email: string | null
  programs: UserProgramLink[]
}

export function AccountPage() {
  const { signOut } = useSession()
  const { data: profile } = useQuery({
    queryKey: ['me'],
    queryFn: () => apiClient.get<Profile>('/me'),
  })
  const [confirming, setConfirming] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const deleteAccount = useMutation({
    mutationFn: () => apiClient.delete('/me'),
    onSuccess: () => void signOut(),
    onError: (err) =>
      setError(err instanceof ApiError ? err.message : 'Failed to delete account'),
  })

  return (
    <main>
      <h1>Account</h1>
      {profile && (
        <section>
          <p>
            <strong>{profile.display_name}</strong> ({profile.email ?? 'no email'}) —{' '}
            {profile.role}
          </p>
          {profile.programs.length > 0 && (
            <p>
              Programs: {profile.programs.map((link) => link.programs.code).join(' + ')}
            </p>
          )}
        </section>
      )}

      <section aria-label="Delete account">
        <h2>Delete my account</h2>
        <p className="page-status">
          Permanently removes your account and all your grades, enrolments, and plans.
        </p>
        {!confirming ? (
          <button type="button" onClick={() => setConfirming(true)}>
            Delete account…
          </button>
        ) : (
          <div className="calculator-actions">
            <p role="alert" className="form-error">
              This cannot be undone. Are you sure?
            </p>
            <button
              type="button"
              onClick={() => deleteAccount.mutate()}
              disabled={deleteAccount.isPending}
            >
              {deleteAccount.isPending ? 'Deleting…' : 'Yes, delete everything'}
            </button>
            <button type="button" onClick={() => setConfirming(false)}>
              Cancel
            </button>
          </div>
        )}
        {error && <p role="alert" className="form-error">{error}</p>}
      </section>
    </main>
  )
}
