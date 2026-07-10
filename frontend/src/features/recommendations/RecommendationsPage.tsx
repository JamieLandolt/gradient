import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import type { FormEvent } from 'react'

import { ApiError, apiClient } from '../../lib/apiClient'
import type { RecommendationSet } from '../../types/api'

export function RecommendationsPage() {
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
    <main>
      <h1>Course recommendations</h1>
      <form onSubmit={handleSubmit} className="inline-form">
        <input
          aria-label="Your interests"
          placeholder="e.g. machine learning, databases"
          value={interests}
          onChange={(e) => setInterests(e.target.value)}
        />
        <button type="submit" disabled={generate.isPending}>
          {generate.isPending
            ? 'Thinking…'
            : hasExisting
              ? 'Regenerate'
              : 'Recommend courses'}
        </button>
      </form>
      {generate.isPending && (
        <p className="page-status" role="status">Generating recommendations…</p>
      )}
      {error && <p role="alert" className="form-error">{error}</p>}
      {shown && (
        <section aria-live="polite">
          {!result && (
            <p className="page-status">Your most recent recommendations:</p>
          )}
          {shown.items.length === 0 && (
            <p className="page-status">No matches — try different interests.</p>
          )}
          <ol className="card-list">
            {shown.items.map((item) => (
              <li key={item.course_code} className="course-card">
                <h2>{item.course_code}</h2>
                <p>{item.reason}</p>
                <p className={`prereq-badge prereq-${item.prereq_status}`}>
                  Prerequisites: {item.prereq_status.replace('_', ' ')}
                </p>
              </li>
            ))}
          </ol>
          <p className="page-status">{shown.disclaimer}</p>
        </section>
      )}
    </main>
  )
}
