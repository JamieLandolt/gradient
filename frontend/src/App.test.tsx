import { render, screen } from '@testing-library/react'
import { vi } from 'vitest'

import { createSupabaseAuthMock } from './testUtils'

vi.mock('./lib/supabase', () => ({ supabase: createSupabaseAuthMock() }))

import App from './App'

test('renders the app shell with the authoritative-records disclaimer', async () => {
  render(<App />)

  expect(await screen.findByRole('heading', { name: 'Gradient' })).toBeInTheDocument()
  expect(screen.getByRole('note')).toHaveTextContent(/official university records/i)
})

test('logged-out nav offers calculator, login, and register', async () => {
  render(<App />)

  const nav = await screen.findByRole('navigation', { name: 'Main' })
  expect(nav).toHaveTextContent('Calculator')
  expect(nav).toHaveTextContent('Log in')
  expect(nav).toHaveTextContent('Register')
})
