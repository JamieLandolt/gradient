import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, test, vi } from 'vitest'

import { createQueryClient } from '../../lib/queryClient'
import { HistoryPage } from './HistoryPage'

function envelope(data: unknown) {
  return { success: true, data, error: null, meta: null }
}

const HISTORY = [
  {
    enrolment_id: 1,
    course_code: 'COMP1100',
    course_title: 'Intro to Programming',
    units: 2,
    year: 2025,
    semester: 'S1',
    status: 'completed',
    final_grade: 6,
    final_percent: 82,
    is_transfer: false,
  },
  {
    enrolment_id: 2,
    course_code: 'COMP2140',
    course_title: 'Software Design',
    units: 2,
    year: 2026,
    semester: 'S1',
    status: 'in_progress',
    final_grade: null,
    final_percent: null,
    is_transfer: false,
  },
]

function mockApi() {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation((url: string) => {
      const path = String(url)
      const data = path.includes('/me/history') ? HISTORY : []
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
        <HistoryPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

test('renders in-progress/planned courses as styled cards with a status badge', async () => {
  mockApi()
  renderPage()

  const heading = await screen.findByText('COMP2140')
  expect(heading.closest('li')).toHaveClass('course-card')
  expect(heading.closest('ul')).toHaveClass('card-list')

  const badge = screen.getByText('in progress')
  expect(badge).toHaveClass('status-badge', 'status-in_progress')
})
