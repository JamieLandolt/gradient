import { QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
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

test('shows a typing indicator that persists after the first chunk arrives', async () => {
  let releaseSecondChunk: () => void = () => {}
  const secondChunkGate = new Promise<void>((resolve) => {
    releaseSecondChunk = resolve
  })

  const stream = new ReadableStream({
    async start(controller) {
      controller.enqueue(new TextEncoder().encode('You need '))
      await secondChunkGate
      controller.enqueue(new TextEncoder().encode('74% on the final.'))
      controller.close()
    },
  })

  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation((url: string) => {
      if (String(url).includes('/assistant/ask/stream')) {
        return Promise.resolve(
          new Response(stream, { status: 200, headers: { 'Content-Type': 'text/plain' } }),
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

  // First chunk has arrived, but the stream isn't finished — the indicator must
  // still be visible, not just in the gap before any text appeared.
  expect(await screen.findByText(/You need/)).toBeInTheDocument()
  expect(document.querySelector('.typing-indicator')).toBeInTheDocument()

  releaseSecondChunk()

  await waitFor(() =>
    expect(document.querySelector('.typing-indicator')).not.toBeInTheDocument(),
  )
  // Scoped to the chat bubble: once streaming ends, the screen-reader status
  // region announces the same final text, so an unscoped text query would
  // ambiguously match both.
  expect(document.querySelector('.chat-assistant p')?.textContent).toBe(
    'You need 74% on the final.',
  )
})
