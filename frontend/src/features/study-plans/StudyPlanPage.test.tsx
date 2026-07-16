import { QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, test, vi } from 'vitest'

import { createQueryClient } from '../../lib/queryClient'
import { StudyPlanPage } from './StudyPlanPage'

function envelope(data: unknown) {
  return { success: true, data, error: null, meta: null }
}

function json(data: unknown, status = 200) {
  return Promise.resolve(
    new Response(JSON.stringify(envelope(data)), {
      status,
      headers: { 'Content-Type': 'application/json' },
    }),
  )
}

const SAVED_SUMMARY = { id: 1, week_start: '2026-08-03', generated_at: null }
const SAVED_PLAN = {
  id: 1,
  week_start: '2026-08-03',
  generated_at: null,
  blocks: [
    {
      day_of_week: 0,
      start_hour: 9,
      focus: 'COMP3506 — Assignment 1 (30% · aiming for 65%)',
      course_code: 'COMP3506',
    },
  ],
  diagnostics: [],
  disclaimer: 'Weekly study plans are advisory.',
}

/** Route fetch by "METHOD path-substring" in `overrides`; records every call. */
function stubApi(overrides: Record<string, () => Promise<Response>> = {}) {
  const calls: { url: string; method: string; body?: string }[] = []
  const fetchMock = vi.fn((url: string, init?: RequestInit) => {
    const method = init?.method ?? 'GET'
    const path = String(url)
    calls.push({ url: path, method, body: init?.body as string | undefined })

    for (const [pattern, handler] of Object.entries(overrides)) {
      const [patternMethod, patternPath] = pattern.split(' ')
      if (method === patternMethod && path.includes(patternPath)) return handler()
    }

    if (method === 'GET' && path.includes('/study-availability')) return json([])
    if (method === 'GET' && path.includes('/study-plans/remaining-assessments')) return json([])
    if (method === 'GET' && /\/study-plans\/\d+$/.test(path)) return json(SAVED_PLAN)
    if (method === 'GET' && path.includes('/study-plans')) return json([SAVED_SUMMARY])
    return json(null, 404)
  })
  vi.stubGlobal('fetch', fetchMock)
  return calls
}

afterEach(() => vi.unstubAllGlobals())

function renderPage() {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter>
        <StudyPlanPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

test('View opens a saved weekly plan inline, and Hide collapses it', async () => {
  stubApi()
  renderPage()

  const viewButton = await screen.findByRole('button', { name: 'View' })
  expect(screen.queryByText('COMP3506')).not.toBeInTheDocument()

  fireEvent.click(viewButton)

  expect(await screen.findByText('COMP3506')).toBeInTheDocument()
  // The specific assignment/task must be visible in the cell itself, not just
  // in a hover-only tooltip.
  expect(screen.getByText('Assignment 1 (30% · aiming for 65%)')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Hide' })).toBeInTheDocument()

  fireEvent.click(screen.getByRole('button', { name: 'Hide' }))
  await waitFor(() => expect(screen.queryByText('COMP3506')).not.toBeInTheDocument())
})

test('clicking an availability slot cycles free -> study -> blocked -> free, and saves', async () => {
  const calls = stubApi({
    'PUT /study-availability': () =>
      json([{ day_of_week: 0, start_hour: 9, slot_type: 'study' }]),
  })
  renderPage()

  const cell = await screen.findByLabelText('Mon 9am')
  expect(cell.className).not.toMatch(/study|blocked/)

  fireEvent.click(cell)
  expect(cell.className).toMatch(/study/)

  fireEvent.click(cell)
  expect(cell.className).toMatch(/blocked/)

  fireEvent.click(cell)
  expect(cell.className).not.toMatch(/study|blocked/)

  fireEvent.click(screen.getByRole('button', { name: 'Save weekly template' }))

  await waitFor(() =>
    expect(
      calls.some((c) => c.method === 'PUT' && c.url.includes('/study-availability')),
    ).toBe(true),
  )
})

test('generating a plan shows its blocks and diagnostics', async () => {
  stubApi({
    'POST /study-plans/generate': () =>
      json({
        id: 2,
        week_start: '2026-08-03',
        generated_at: null,
        blocks: [
          {
            day_of_week: 1,
            start_hour: 10,
            focus: 'MATH1051 — Quiz (20% · aiming for 65%)',
            course_code: 'MATH1051',
          },
        ],
        diagnostics: [{ severity: 'info', message: 'Only 1 course was eligible this week.' }],
        disclaimer: 'Weekly study plans are advisory.',
      }),
  })
  renderPage()

  fireEvent.click(await screen.findByRole('button', { name: 'Generate' }))

  expect(await screen.findByText('MATH1051')).toBeInTheDocument()
  expect(screen.getByText('Only 1 course was eligible this week.')).toBeInTheDocument()
})
