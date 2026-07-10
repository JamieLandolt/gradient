import { QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, test, vi } from 'vitest'

import { createQueryClient } from '../../lib/queryClient'
import { PlannerPage } from './PlannerPage'

function envelope(data: unknown) {
  return { success: true, data, error: null, meta: null }
}

const SAVED_PLAN = {
  id: 1,
  name: 'My CS plan',
  feasible: true,
  generated_at: null,
  semesters: [
    {
      year: 2026,
      semester: 'S1',
      label: '2026 S1',
      entries: [{ course_code: 'CSSE1001', units: 2, explanation: 'placed first' }],
    },
  ],
  diagnostics: [],
}

function mockApi() {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation((url: string) => {
      const path = String(url)
      let data: unknown = []
      if (/\/planner\/plans\/\d+$/.test(path)) {
        data = SAVED_PLAN // detail (must be checked before the list route)
      } else if (path.includes('/planner/plans')) {
        data = [{ id: 1, name: 'My CS plan', feasible: true, generated_at: null }]
      } else if (path.includes('/programs') || path.includes('/prereq-status')) {
        data = []
      }
      return Promise.resolve(
        new Response(JSON.stringify(envelope(data)), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      )
    }),
  )
}

afterEach(() => vi.unstubAllGlobals())

function renderPage() {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter>
        <PlannerPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

test('View opens a saved plan inline, and Hide collapses it', async () => {
  mockApi()
  renderPage()

  // The saved plan appears; its detail is not shown until View is clicked.
  const viewButton = await screen.findByRole('button', { name: 'View' })
  expect(screen.queryByText('CSSE1001')).not.toBeInTheDocument()

  fireEvent.click(viewButton)

  // Detail fetched and rendered inline under the card.
  expect(await screen.findByText(/CSSE1001/)).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Hide' })).toBeInTheDocument()

  fireEvent.click(screen.getByRole('button', { name: 'Hide' }))
  await waitFor(() => expect(screen.queryByText('CSSE1001')).not.toBeInTheDocument())
})
