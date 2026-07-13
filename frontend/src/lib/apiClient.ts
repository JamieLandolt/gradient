/**
 * Typed fetch wrapper for the Gradient API.
 *
 * Every backend response uses the envelope {success, data, error, meta}.
 * This client unwraps it: resolves with `data` on success, throws ApiError
 * (with the server's user-facing message) on failure.
 */

export interface ApiEnvelope<T> {
  success: boolean
  data: T | null
  error: string | null
  meta: Record<string, unknown> | null
}

export class ApiError extends Error {
  readonly status: number
  readonly meta: Record<string, unknown> | null

  constructor(message: string, status: number, meta: Record<string, unknown> | null = null) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.meta = meta
  }
}

export type AccessTokenProvider = () => Promise<string | null>

const API_BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000/api/v1'

/** Guards the connection + response-headers phase so a hung call can't freeze the UI. */
const REQUEST_TIMEOUT_MS = 20_000

let tokenProvider: AccessTokenProvider = async () => null

/**
 * fetch() that aborts if no response headers arrive within REQUEST_TIMEOUT_MS.
 * The timer is cleared once the Response is in hand, so a long streamed body
 * (the assistant) is never cut off mid-stream.
 */
async function fetchWithTimeout(url: string, init: RequestInit): Promise<Response> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS)
  try {
    return await fetch(url, { ...init, signal: controller.signal })
  } catch {
    if (controller.signal.aborted) {
      throw new ApiError('The server took too long to respond — please try again.', 0)
    }
    throw new ApiError('Cannot reach the Gradient server. Check your connection.', 0)
  } finally {
    clearTimeout(timer)
  }
}

/** Called once at app start-up with a function returning the Supabase access token. */
export function setAccessTokenProvider(provider: AccessTokenProvider): void {
  tokenProvider = provider
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = await tokenProvider()
  const headers = new Headers(init.headers)
  // Let the browser set multipart boundaries for FormData uploads; only JSON
  // bodies need an explicit content type.
  if (!(init.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json')
  }
  if (token) {
    headers.set('Authorization', `Bearer ${token}`)
  }

  const response = await fetchWithTimeout(`${API_BASE_URL}${path}`, { ...init, headers })

  let body: ApiEnvelope<T>
  try {
    body = (await response.json()) as ApiEnvelope<T>
  } catch {
    throw new ApiError('Unexpected response from the server.', response.status)
  }

  if (!response.ok || !body.success) {
    throw new ApiError(body.error ?? 'Something went wrong.', response.status, body.meta)
  }
  return body.data as T
}

export const apiClient = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, payload?: unknown) =>
    request<T>(path, { method: 'POST', body: payload === undefined ? undefined : JSON.stringify(payload) }),
  postForm: <T>(path: string, form: FormData) =>
    request<T>(path, { method: 'POST', body: form }),
  put: <T>(path: string, payload?: unknown) =>
    request<T>(path, { method: 'PUT', body: payload === undefined ? undefined : JSON.stringify(payload) }),
  patch: <T>(path: string, payload?: unknown) =>
    request<T>(path, { method: 'PATCH', body: payload === undefined ? undefined : JSON.stringify(payload) }),
  delete: <T>(path: string) => request<T>(path, { method: 'DELETE' }),
}

/** The current Supabase access token, for callers that bypass the JSON wrapper. */
export async function getAccessToken(): Promise<string | null> {
  return tokenProvider()
}

/**
 * POST that streams a plain-text response body, invoking `onChunk` as bytes
 * arrive (used by the assistant). Errors are still JSON envelopes, so a non-OK
 * response is unwrapped into an ApiError like every other call.
 */
export async function streamPost(
  path: string,
  payload: unknown,
  onChunk: (text: string) => void,
): Promise<void> {
  const token = await tokenProvider()
  const headers = new Headers({ 'Content-Type': 'application/json' })
  if (token) {
    headers.set('Authorization', `Bearer ${token}`)
  }

  const response = await fetchWithTimeout(`${API_BASE_URL}${path}`, {
    method: 'POST',
    headers,
    body: JSON.stringify(payload),
  })

  if (!response.ok) {
    let message = 'The assistant is unavailable right now.'
    try {
      const body = (await response.json()) as ApiEnvelope<unknown>
      message = body.error ?? message
    } catch {
      /* error body was not JSON — keep the generic message */
    }
    throw new ApiError(message, response.status)
  }

  if (!response.body) {
    onChunk(await response.text())
    return
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    if (value) onChunk(decoder.decode(value, { stream: true }))
  }
  const tail = decoder.decode()
  if (tail) onChunk(tail)
}
