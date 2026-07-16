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

test('generating a plan sends the selected study load, and hides warnings behind a toggle', async () => {
  const GENERATED_PLAN = {
    feasible: true,
    semesters: [
      {
        year: 2026,
        semester: 'S1',
        label: '2026 S1',
        entries: [{ course_code: 'MATH1051', units: 2, explanation: 'no prerequisites' }],
      },
    ],
    diagnostics: [
      { severity: 'info', message: 'Only 1 course was eligible in 2026 S1 — you have taken everything else you are currently eligible for.' },
      { severity: 'warning', message: 'MATH1051 has a prerequisite that could not be parsed; check the course profile manually.' },
    ],
  }
  let lastSequenceBody: unknown = null

  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      const path = String(url)
      if (path.includes('/planner/sequence') && init?.method === 'POST') {
        lastSequenceBody = JSON.parse(init.body as string)
        return Promise.resolve(
          new Response(JSON.stringify(envelope(GENERATED_PLAN)), {
            status: 200,
            headers: { 'Content-Type': 'application/json' },
          }),
        )
      }
      return Promise.resolve(
        new Response(JSON.stringify(envelope([])), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      )
    }),
  )

  renderPage()

  const studyLoadSelect = await screen.findByLabelText('Study load')
  expect(studyLoadSelect).toHaveValue('full_time')
  fireEvent.change(studyLoadSelect, { target: { value: 'part_time' } })

  fireEvent.click(screen.getByRole('button', { name: 'Generate plan' }))

  // The info diagnostic is visible immediately; the warning is collapsed
  // behind a <details> toggle instead of dumped inline. jsdom doesn't apply
  // the UA stylesheet that hides <details> content, so check visibility
  // (which jest-dom derives from the `open` property) rather than presence.
  expect(await screen.findByText(/Only 1 course was eligible/)).toBeVisible()
  expect(screen.getByText(/could not be parsed/)).not.toBeVisible()

  fireEvent.click(screen.getByText('1 prerequisite needs manual checking'))
  expect(await screen.findByText(/could not be parsed/)).toBeVisible()

  expect(lastSequenceBody).toMatchObject({ study_load: 'part_time' })
})
