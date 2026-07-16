import { QueryClientProvider } from '@tanstack/react-query'
import { act, render, waitFor } from '@testing-library/react'
import { expect, test, vi } from 'vitest'

import { createQueryClient } from '../../lib/queryClient'
import { SessionProvider } from './SessionProvider'

const mocks = vi.hoisted(() => ({
  authCallback: null as ((event: string, session: unknown) => void) | null,
}))

vi.mock('../../lib/supabase', () => ({
  supabase: {
    auth: {
      getSession: vi.fn().mockResolvedValue({ data: { session: null } }),
      onAuthStateChange: vi.fn((cb: (event: string, session: unknown) => void) => {
        mocks.authCallback = cb
        return { data: { subscription: { unsubscribe: vi.fn() } } }
      }),
      signInWithPassword: vi.fn().mockResolvedValue({ error: null }),
      signUp: vi.fn().mockResolvedValue({ error: null }),
      signOut: vi.fn().mockResolvedValue({ error: null }),
    },
  },
}))

const sessionFor = (id: string) => ({ user: { id }, access_token: `token-${id}` })

async function renderProvider() {
  const queryClient = createQueryClient()
  render(
    <QueryClientProvider client={queryClient}>
      <SessionProvider>
        <div>app</div>
      </SessionProvider>
    </QueryClientProvider>,
  )
  await waitFor(() => expect(mocks.authCallback).not.toBeNull())
  return queryClient
}

/** Stand in for a page's cached private data, e.g. Alice's enrolments. */
function seedCache(queryClient: ReturnType<typeof createQueryClient>) {
  queryClient.setQueryData(['enrolments'], [{ course_code: 'CSSE1001' }])
  queryClient.setQueryData(['gpa'], { gpa: 6.75 })
}

test('signing in as a different user drops the previous user’s cached data', async () => {
  const queryClient = await renderProvider()
  act(() => mocks.authCallback!('SIGNED_IN', sessionFor('alice')))
  seedCache(queryClient)

  act(() => mocks.authCallback!('SIGNED_IN', sessionFor('bob')))

  expect(queryClient.getQueryData(['enrolments'])).toBeUndefined()
  expect(queryClient.getQueryData(['gpa'])).toBeUndefined()
})

test('signing out drops the cached data', async () => {
  const queryClient = await renderProvider()
  act(() => mocks.authCallback!('SIGNED_IN', sessionFor('alice')))
  seedCache(queryClient)

  act(() => mocks.authCallback!('SIGNED_OUT', null))

  expect(queryClient.getQueryData(['enrolments'])).toBeUndefined()
})

test('a token refresh for the same user keeps the cache', async () => {
  const queryClient = await renderProvider()
  act(() => mocks.authCallback!('SIGNED_IN', sessionFor('alice')))
  seedCache(queryClient)

  act(() => mocks.authCallback!('TOKEN_REFRESHED', sessionFor('alice')))

  expect(queryClient.getQueryData(['enrolments'])).toEqual([{ course_code: 'CSSE1001' }])
  expect(queryClient.getQueryData(['gpa'])).toEqual({ gpa: 6.75 })
})
