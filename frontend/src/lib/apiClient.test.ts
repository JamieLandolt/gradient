import { afterEach, expect, test, vi } from 'vitest'

import { ApiError, apiClient, setAccessTokenProvider } from './apiClient'

function mockFetchOnce(status: number, body: unknown) {
  const response = new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
  const fetchMock = vi.fn().mockResolvedValue(response)
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

afterEach(() => {
  vi.unstubAllGlobals()
  setAccessTokenProvider(async () => null)
})

test('unwraps data from a successful envelope', async () => {
  mockFetchOnce(200, { success: true, data: { status: 'ok' }, error: null, meta: null })

  const data = await apiClient.get<{ status: string }>('/health')

  expect(data).toEqual({ status: 'ok' })
})

test('throws ApiError with the server message on a failed envelope', async () => {
  mockFetchOnce(404, { success: false, data: null, error: 'Course not found', meta: null })

  await expect(apiClient.get('/courses/NOPE1000')).rejects.toThrowError(
    new ApiError('Course not found', 404),
  )
})

test('attaches the bearer token from the access-token provider', async () => {
  const fetchMock = mockFetchOnce(200, { success: true, data: null, error: null, meta: null })
  setAccessTokenProvider(async () => 'jwt-token-123')

  await apiClient.get('/me')

  const headers = new Headers((fetchMock.mock.calls[0][1] as RequestInit).headers)
  expect(headers.get('Authorization')).toBe('Bearer jwt-token-123')
})

test('serialises POST payloads as JSON', async () => {
  const fetchMock = mockFetchOnce(200, { success: true, data: null, error: null, meta: null })

  await apiClient.post('/enrolments', { courseCode: 'COMP1000' })

  const init = fetchMock.mock.calls[0][1] as RequestInit
  expect(init.method).toBe('POST')
  expect(JSON.parse(init.body as string)).toEqual({ courseCode: 'COMP1000' })
})

test('wraps network failures in a friendly ApiError', async () => {
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('fetch failed')))

  await expect(apiClient.get('/health')).rejects.toMatchObject({
    name: 'ApiError',
    status: 0,
  })
})
