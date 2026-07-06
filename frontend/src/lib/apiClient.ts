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

let tokenProvider: AccessTokenProvider = async () => null

/** Called once at app start-up with a function returning the Supabase access token. */
export function setAccessTokenProvider(provider: AccessTokenProvider): void {
  tokenProvider = provider
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = await tokenProvider()
  const headers = new Headers(init.headers)
  headers.set('Content-Type', 'application/json')
  if (token) {
    headers.set('Authorization', `Bearer ${token}`)
  }

  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}${path}`, { ...init, headers })
  } catch {
    throw new ApiError('Cannot reach the Gradient server. Check your connection.', 0)
  }

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
  put: <T>(path: string, payload?: unknown) =>
    request<T>(path, { method: 'PUT', body: payload === undefined ? undefined : JSON.stringify(payload) }),
  patch: <T>(path: string, payload?: unknown) =>
    request<T>(path, { method: 'PATCH', body: payload === undefined ? undefined : JSON.stringify(payload) }),
  delete: <T>(path: string) => request<T>(path, { method: 'DELETE' }),
}
