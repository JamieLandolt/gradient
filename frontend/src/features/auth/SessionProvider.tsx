import { useQueryClient } from '@tanstack/react-query'
import type { Session } from '@supabase/supabase-js'
import { createContext, useContext, useEffect, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'

import { setAccessTokenProvider } from '../../lib/apiClient'
import { supabase } from '../../lib/supabase'

interface SessionContextValue {
  session: Session | null
  isLoading: boolean
  signIn: (email: string, password: string) => Promise<string | null>
  signUp: (email: string, password: string, displayName: string) => Promise<string | null>
  signOut: () => Promise<void>
}

const SessionContext = createContext<SessionContextValue | null>(null)

export function SessionProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const queryClient = useQueryClient()
  const currentUserId = useRef<string | null>(null)

  useEffect(() => {
    setAccessTokenProvider(async () => {
      const { data } = await supabase.auth.getSession()
      return data.session?.access_token ?? null
    })

    supabase.auth
      .getSession()
      .then(({ data }) => {
        currentUserId.current = data.session?.user.id ?? null
        setSession(data.session)
      })
      // Without this, a rejection leaves isLoading true forever and every
      // protected route sits on "Loading your session…" with no way out.
      // Treat an unreadable session as no session: the user can log in again.
      .catch(() => {
        currentUserId.current = null
        setSession(null)
      })
      .finally(() => setIsLoading(false))

    const { data: subscription } = supabase.auth.onAuthStateChange((_event, newSession) => {
      const nextUserId = newSession?.user.id ?? null
      // Every cached query holds one user's private data. Drop the whole cache
      // whenever the identity behind it changes, or the next person to log in
      // on this tab sees the previous user's courses and GPA on first paint.
      // Keyed on the user id, not the event: a token refresh re-fires this with
      // the same user and must not wipe a healthy cache.
      if (nextUserId !== currentUserId.current) {
        currentUserId.current = nextUserId
        queryClient.clear()
      }
      setSession(newSession)
    })
    return () => subscription.subscription.unsubscribe()
  }, [queryClient])

  const value = useMemo<SessionContextValue>(
    () => ({
      session,
      isLoading,
      signIn: async (email, password) => {
        const { error } = await supabase.auth.signInWithPassword({ email, password })
        return error ? error.message : null
      },
      signUp: async (email, password, displayName) => {
        const { error } = await supabase.auth.signUp({
          email,
          password,
          options: { data: { display_name: displayName } },
        })
        return error ? error.message : null
      },
      signOut: async () => {
        await supabase.auth.signOut()
      },
    }),
    [session, isLoading],
  )

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>
}

export function useSession(): SessionContextValue {
  const context = useContext(SessionContext)
  if (!context) {
    throw new Error('useSession must be used inside SessionProvider')
  }
  return context
}
