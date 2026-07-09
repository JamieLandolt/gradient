import { QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, test, vi } from 'vitest'

import { createQueryClient } from '../../lib/queryClient'
import { AssistantPage } from './AssistantPage'

function envelope(data: unknown) {
  return { success: true, data, error: null, meta: null }
}

afterEach(() => vi.unstubAllGlobals())

function renderPage() {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter>
        <AssistantPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

test('streams the assistant answer into a chat bubble', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation((url: string) => {
      if (String(url).includes('/assistant/ask/stream')) {
        return Promise.resolve(
          new Response('You need 74% on the final.', {
            status: 200,
            headers: { 'Content-Type': 'text/plain' },
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

  const input = await screen.findByLabelText('Your question')
  fireEvent.change(input, { target: { value: 'How am I doing?' } })
  fireEvent.click(screen.getByRole('button', { name: 'Ask' }))

  expect(await screen.findByText('You need 74% on the final.')).toBeInTheDocument()
  expect(screen.getByText('How am I doing?')).toBeInTheDocument()
})
