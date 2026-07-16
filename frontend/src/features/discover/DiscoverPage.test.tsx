import { QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, test, vi } from 'vitest'

import { createQueryClient } from '../../lib/queryClient'
import { DiscoverPage } from './DiscoverPage'

function envelope(data: unknown) {
  return { success: true, data, error: null, meta: null }
}

const SEARCH_RESULTS = [
  { course_id: 1, code: 'COMP3702', title: 'Artificial Intelligence', description: 'agents search', similarity: 0.9 },
]

const RECOMMENDATION_SET = {
  id: 1,
  generated_at: null,
  provider: 'mock',
  items: [
    { course_code: 'COMP4702', rank: 1, reason: 'Matches your interests', prereq_status: 'met' },
  ],
  disclaimer: 'Recommendations are advisory only.',
}

function mockApi() {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation((url: string) => {
      const path = String(url)
      let data: unknown = null
      if (path.includes('/search/courses')) {
        data = SEARCH_RESULTS
      } else if (path.includes('/recommendations/generate') || path.includes('/recommendations/latest')) {
        data = RECOMMENDATION_SET
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
        <DiscoverPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

test('defaults to Search mode and can switch to Recommend for me', async () => {
  mockApi()
  renderPage()

  expect(screen.getByRole('tab', { name: 'Search' })).toHaveAttribute('aria-selected', 'true')
  fireEvent.change(screen.getByLabelText('Search query'), { target: { value: 'ai' } })
  fireEvent.click(screen.getByRole('button', { name: 'Search' }))
  expect(await screen.findByText('COMP3702')).toBeInTheDocument()

  fireEvent.click(screen.getByRole('tab', { name: 'Recommend for me' }))
  expect(screen.queryByText('COMP3702')).not.toBeInTheDocument()
  expect(await screen.findByText('COMP4702')).toBeInTheDocument()
  expect(screen.getByText('Matches your interests')).toBeInTheDocument()
})
