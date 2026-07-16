import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, test, vi } from 'vitest'

import { createQueryClient } from '../../lib/queryClient'
import { ImportPage } from './ImportPage'

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

const QUEUED = { id: 42, status: 'queued', course_code: '', profile_version_id: null }
const EXTRACTED = { id: 42, status: 'extracted', course_code: 'COMP2140', profile_version_id: 100 }
const FAILED = {
  id: 42,
  status: 'failed',
  course_code: '',
  profile_version_id: null,
  error: 'Could not find a valid course code',
}

/**
 * Route fetch by path + method; records calls. `jobPolls` is the sequence of job
 * bodies returned by successive GET /ingestion/jobs/{id} calls (last one repeats),
 * so tests can drive the real queued -> re-poll -> terminal transition.
 */
function stubApi(jobPolls: unknown[] = [EXTRACTED]) {
  const calls: { url: string; method: string }[] = []
  let pollIndex = 0
  const fetchMock = vi.fn((url: string, init?: RequestInit) => {
    const method = init?.method ?? 'GET'
    calls.push({ url: String(url), method })
    if (String(url).includes('/curator/profile-versions')) return json([])
    if (String(url).includes('/ingestion/jobs/')) {
      const body = jobPolls[Math.min(pollIndex, jobPolls.length - 1)]
      pollIndex += 1
      return json(body)
    }
    if (
      String(url).includes('/ingestion/jobs') ||
      String(url).includes('/ingestion/uploads') ||
      String(url).includes('/ingestion/from-url')
    ) {
      return json(QUEUED, 201)
    }
    return json(null, 404)
  })
  vi.stubGlobal('fetch', fetchMock)
  return calls
}

function renderPage() {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <ImportPage />
    </QueryClientProvider>,
  )
}

afterEach(() => vi.unstubAllGlobals())

test('shows the queued state then the extracted result as polling progresses', async () => {
  stubApi([QUEUED, EXTRACTED])
  renderPage()

  await userEvent.type(screen.getByLabelText('Course profile text'), 'Course code: COMP2140')
  await userEvent.click(screen.getByRole('button', { name: 'Extract' }))

  // The first poll returns a still-queued job → the interim state renders.
  expect(await screen.findByText(/Queued/)).toBeInTheDocument()
  // A later poll returns the terminal job → the extracted result renders.
  expect(
    await screen.findByText('COMP2140: extracted', undefined, { timeout: 3000 }),
  ).toBeInTheDocument()
})

test('renders a failure message when the background job fails', async () => {
  stubApi([FAILED])
  renderPage()

  await userEvent.type(screen.getByLabelText('Course profile text'), 'garbage with no code')
  await userEvent.click(screen.getByRole('button', { name: 'Extract' }))

  expect(await screen.findByText(/Extraction failed:/)).toBeInTheDocument()
})

test('entering a course code posts to the from-url endpoint and disables paste/upload', async () => {
  const calls = stubApi([EXTRACTED])
  renderPage()

  await userEvent.type(screen.getByLabelText('Course code (fetches automatically)'), 'COMP3506')

  // Entering a course code switches the input mode: paste + upload disable.
  expect(screen.getByLabelText('Course profile text')).toBeDisabled()
  expect(screen.getByLabelText('…or upload a PDF or .txt')).toBeDisabled()

  await userEvent.click(screen.getByRole('button', { name: 'Extract' }))

  expect(await screen.findByText('COMP2140: extracted')).toBeInTheDocument()
  await waitFor(() =>
    expect(
      calls.some((c) => c.url.includes('/ingestion/from-url') && c.method === 'POST'),
    ).toBe(true),
  )
})

test('uploading a PDF posts to the upload endpoint and disables the paste box', async () => {
  const calls = stubApi([EXTRACTED])
  renderPage()

  const file = new File([new Uint8Array([1, 2, 3])], 'profile.pdf', { type: 'application/pdf' })
  await userEvent.upload(screen.getByLabelText('…or upload a PDF or .txt'), file)

  // Selecting a file switches the input mode: the paste box is disabled.
  expect(screen.getByLabelText('Course profile text')).toBeDisabled()

  await userEvent.click(screen.getByRole('button', { name: 'Extract' }))

  expect(await screen.findByText('COMP2140: extracted')).toBeInTheDocument()
  await waitFor(() =>
    expect(
      calls.some((c) => c.url.includes('/ingestion/uploads') && c.method === 'POST'),
    ).toBe(true),
  )
})
