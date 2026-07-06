import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, test, vi } from 'vitest'

import { createQueryClient } from '../../lib/queryClient'
import { DashboardPage } from './DashboardPage'

function envelope(data: unknown) {
  return { success: true, data, error: null, meta: null }
}

function mockApi() {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation((url: string) => {
      let data: unknown = []
      if (String(url).includes('/enrolments')) {
        data = [
          {
            enrolment_id: 1,
            course_code: 'CSSE1001',
            course_title: 'Intro to Software Engineering',
            units: 2,
            year: 2026,
            semester: 'S1',
            status: 'in_progress',
            final_grade: null,
            final_percent: null,
            is_transfer: false,
          },
        ]
      } else if (String(url).includes('/me/gpa')) {
        data = { gpa: 5.5, completed_courses: 4, total_units: 8 }
      } else if (String(url).includes('/courses')) {
        data = [{ id: 1, code: 'CSSE1001', title: 'Intro', units: 2, description: '' }]
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

test('shows GPA summary and in-progress course cards', async () => {
  mockApi()
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter>
        <DashboardPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )

  expect(await screen.findByText('CSSE1001')).toBeInTheDocument()
  expect(screen.getByLabelText('GPA summary')).toHaveTextContent('5.50')
  expect(screen.getByLabelText('Add course')).toBeInTheDocument()
})
