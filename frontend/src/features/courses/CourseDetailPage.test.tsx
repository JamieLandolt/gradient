import { QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, expect, test, vi } from 'vitest'

import { createQueryClient } from '../../lib/queryClient'
import { CourseDetailPage } from './CourseDetailPage'

function envelope(data: unknown) {
  return { success: true, data, error: null, meta: null }
}

const STANDING = {
  enrolment_id: 1,
  secured_percent: 16,
  remaining_weight: 50,
  best_case_percent: 66,
  worst_case_percent: 16,
  projected_percent: 40,
  projected_grade: 4,
  items: [
    {
      id: 1,
      source: 'profile',
      name: 'Assignment 1',
      weight: 20,
      max_mark: 100,
      due_date: '2026-03-27',
      hurdle_min_percent: null,
      hurdle_description: null,
      score: 80,
    },
    {
      id: 3,
      source: 'profile',
      name: 'Final Exam',
      weight: 50,
      max_mark: 100,
      due_date: '2026-06-12',
      hurdle_min_percent: 40,
      hurdle_description: 'Must reach 40%',
      score: null,
    },
  ],
}

const REQUIRED = {
  target_grade: 5,
  target_percent: 65,
  status: 'reachable',
  required_average_percent: 74,
  per_item: [{ name: 'Final Exam', weight: 50, required_percent: 74 }],
  hurdle_blocked: false,
  hurdle_warnings: [],
  final_percent: null,
  final_grade: null,
}

afterEach(() => vi.unstubAllGlobals())

test('renders the standing + assessment table and computes required marks', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation((url: string) => {
      const data = String(url).includes('/required-marks') ? REQUIRED : STANDING
      return Promise.resolve(
        new Response(JSON.stringify(envelope(data)), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      )
    }),
  )

  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={['/courses/1']}>
        <Routes>
          <Route path="/courses/:enrolmentId" element={<CourseDetailPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )

  // Assessment table rendered from the standing.
  expect(await screen.findByText('Assignment 1')).toBeInTheDocument()
  expect(screen.getByRole('heading', { name: 'What do I need?' })).toBeInTheDocument()

  // Target calculator returns a reachable status with the required average.
  fireEvent.click(screen.getByRole('button', { name: 'Calculate' }))
  expect(await screen.findByText('Reachable')).toBeInTheDocument()
  expect(screen.getAllByText(/74\.0%/).length).toBeGreaterThan(0)
})
