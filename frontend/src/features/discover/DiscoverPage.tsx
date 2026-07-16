import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import type { FormEvent } from 'react'

import { ApiError, apiClient } from '../../lib/apiClient'
import type { RecommendationSet, SearchResult } from '../../types/api'

type Mode = 'search' | 'recommend'

function CourseResultCard({
  code,
  title,
  description,
  reason,
  prereqStatus,
}: {
  code: string
  title?: string
  description?: string
  reason?: string
  prereqStatus?: string
}) {
  return (
    <li className="course-card">
      <h2>{code}</h2>
      {title && <p>{title}</p>}
      {reason && <p>{reason}</p>}
      {description && <p className="page-status">{description}</p>}
      {prereqStatus && (
        <p className={`prereq-badge prereq-${prereqStatus}`}>
          Prerequisites: {prereqStatus.replace('_', ' ')}
        </p>
      )}
    </li>
  )
}

function SearchSection() {
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
    <>
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
      {error && (
        <p role="alert" className="form-error">
          {error}
        </p>
      )}
      {results && results.length === 0 && (
        <p className="page-status" aria-live="polite">No matches.</p>
      )}
      {results && results.length > 0 && (
        <ul className="card-list" aria-live="polite">
          {results.map((result) => (
            <CourseResultCard
              key={result.course_id}
              code={result.code}
              title={result.title}
              description={result.description}
            />
          ))}
        </ul>
      )}
    </>
  )
}

function RecommendSection() {
  const queryClient = useQueryClient()
  const { data: latest } = useQuery({
    queryKey: ['recommendations-latest'],
    queryFn: () => apiClient.get<RecommendationSet | null>('/recommendations/latest'),
  })
  const [interests, setInterests] = useState('')
  const [result, setResult] = useState<RecommendationSet | null>(null)
  const [error, setError] = useState<string | null>(null)

  const generate = useMutation({
    mutationFn: () =>
      apiClient.post<RecommendationSet>('/recommendations/generate', {
        interests: interests
          .split(',')
          .map((term) => term.trim())
          .filter(Boolean),
        limit: 5,
      }),
    onSuccess: (data) => {
      setResult(data)
      setError(null)
      void queryClient.invalidateQueries({ queryKey: ['recommendations-latest'] })
    },
    onError: (err) =>
      setError(err instanceof ApiError ? err.message : 'Could not generate recommendations'),
  })

  const shown = result ?? latest ?? null
  const hasExisting = Boolean(shown)

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    generate.mutate()
  }

  return (
    <>
      <p>Tell us your interests and get a ranked shortlist, grounded in your real prerequisite status.</p>
      <form onSubmit={handleSubmit} className="inline-form">
        <input
          aria-label="Your interests"
          placeholder="e.g. machine learning, databases"
          value={interests}
          onChange={(e) => setInterests(e.target.value)}
        />
        <button type="submit" disabled={generate.isPending}>
          {generate.isPending ? 'Thinking…' : hasExisting ? 'Regenerate' : 'Recommend courses'}
        </button>
      </form>
      {generate.isPending && (
        <p className="page-status" role="status">
          Generating recommendations…
        </p>
      )}
      {error && (
        <p role="alert" className="form-error">
          {error}
        </p>
      )}
      {shown && (
        <section aria-live="polite">
          {!result && <p className="page-status">Your most recent recommendations:</p>}
          {shown.items.length === 0 && (
            <p className="page-status">No matches — try different interests.</p>
          )}
          <ol className="card-list">
            {shown.items.map((item) => (
              <CourseResultCard
                key={item.course_code}
                code={item.course_code}
                reason={item.reason}
                prereqStatus={item.prereq_status}
              />
            ))}
          </ol>
          <p className="page-status">{shown.disclaimer}</p>
        </section>
      )}
    </>
  )
}

export function DiscoverPage() {
  const [mode, setMode] = useState<Mode>('search')

  return (
    <main>
      <h1>Find courses</h1>
      <div className="mode-toggle" role="tablist" aria-label="Discovery mode">
        <button
          type="button"
          role="tab"
          aria-selected={mode === 'search'}
          className={mode === 'search' ? 'mode-tab active' : 'mode-tab'}
          onClick={() => setMode('search')}
        >
          Search
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={mode === 'recommend'}
          className={mode === 'recommend' ? 'mode-tab active' : 'mode-tab'}
          onClick={() => setMode('recommend')}
        >
          Recommend for me
        </button>
      </div>
      {mode === 'search' ? <SearchSection /> : <RecommendSection />}
    </main>
  )
}
