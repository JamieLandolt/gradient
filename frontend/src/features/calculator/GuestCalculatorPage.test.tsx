import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, test, vi } from 'vitest'

import { GuestCalculatorPage } from './GuestCalculatorPage'

function mockWhatIfResponse(body: unknown, status = 200) {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(
      new Response(JSON.stringify(body), {
        status,
        headers: { 'Content-Type': 'application/json' },
      }),
    ),
  )
}

afterEach(() => vi.unstubAllGlobals())

test('submits the structure and shows the required average', async () => {
  mockWhatIfResponse({
    success: true,
    error: null,
    meta: null,
    data: {
      status: 'reachable',
      target_grade: 4,
      target_percent: 50,
      required_average_percent: 30,
      hurdle_warnings: [],
      final_grade: null,
      standing: { secured_percent: 32, remaining_weight: 60 },
    },
  })
  const user = userEvent.setup()
  render(<GuestCalculatorPage />)

  await user.type(screen.getByLabelText('Item 1 score'), '80')
  await user.click(screen.getByRole('button', { name: 'Calculate' }))

  expect(await screen.findByRole('heading', { name: 'Reachable' })).toBeInTheDocument()
  expect(screen.getByText(/30\.0%/)).toBeInTheDocument()
  expect(screen.getByText(/32\.0%/)).toBeInTheDocument()
})

test('shows the server validation message when weights are wrong', async () => {
  mockWhatIfResponse(
    {
      success: false,
      data: null,
      error: 'Assessment weights must sum to 100, got 90',
      meta: null,
    },
    422,
  )
  const user = userEvent.setup()
  render(<GuestCalculatorPage />)

  await user.click(screen.getByRole('button', { name: 'Calculate' }))

  expect(await screen.findByRole('alert')).toHaveTextContent(/sum to 100/)
})

test('surfaces hurdle warnings prominently', async () => {
  mockWhatIfResponse({
    success: true,
    error: null,
    meta: null,
    data: {
      status: 'reachable',
      target_grade: 4,
      target_percent: 50,
      required_average_percent: 20,
      hurdle_warnings: ["Hurdle not met on 'Final Exam': scored 30%."],
      final_grade: null,
      standing: { secured_percent: 47.5, remaining_weight: 40 },
    },
  })
  const user = userEvent.setup()
  render(<GuestCalculatorPage />)

  await user.click(screen.getByRole('button', { name: 'Calculate' }))

  expect(await screen.findByText(/Hurdle not met on 'Final Exam'/)).toBeInTheDocument()
})
