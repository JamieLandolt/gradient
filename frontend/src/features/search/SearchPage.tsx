import { useMutation } from '@tanstack/react-query'
import { useState } from 'react'
import type { FormEvent } from 'react'

import { ApiError, apiClient } from '../../lib/apiClient'
import type { SearchResult } from '../../types/api'

export function SearchPage() {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<SearchResult[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  const search = useMutation({
    mutationFn: () =>
      apiClient.get<SearchResult[]>(`/search/courses?q=${encodeURIComponent(query)}`),
    onSuccess: (data) => {
      setResults(data)
      setError(null)
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : 'Search failed'),
  })

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (query.trim()) search.mutate()
  }

  return (
    <main>
      <h1>Find courses</h1>
      <p>Search by meaning — try "machine learning" or "sustainability".</p>
      <form onSubmit={handleSubmit} className="inline-form" role="search">
        <input
          aria-label="Search query"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="What do you want to learn?"
        />
        <button type="submit" disabled={search.isPending}>
          {search.isPending ? 'Searching…' : 'Search'}
        </button>
      </form>
      {error && <p role="alert" className="form-error">{error}</p>}
      {results && (
        <ul className="card-list" aria-live="polite">
          {results.length === 0 && <p className="page-status">No matches.</p>}
          {results.map((result) => (
            <li key={result.course_id} className="course-card">
              <h2>{result.code}</h2>
              <p>{result.title}</p>
              <p className="page-status">{result.description}</p>
            </li>
          ))}
        </ul>
      )}
    </main>
  )
}
