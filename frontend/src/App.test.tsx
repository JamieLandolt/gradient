import { render, screen } from '@testing-library/react'

import App from './App'

test('renders the app shell with the authoritative-records disclaimer', () => {
  render(<App />)

  expect(screen.getByRole('heading', { name: 'Gradient' })).toBeInTheDocument()
  expect(screen.getByRole('note')).toHaveTextContent(/official university records/i)
})
