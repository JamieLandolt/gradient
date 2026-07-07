import { useMutation } from '@tanstack/react-query'
import { useState } from 'react'
import type { FormEvent } from 'react'

import { ApiError, apiClient } from '../../lib/apiClient'
import type { RecommendationSet } from '../../types/api'

export function RecommendationsPage() {
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
    },
    onError: (err) =>
      setError(err instanceof ApiError ? err.message : 'Could not generate recommendations'),
  })

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
          {generate.isPending ? 'Thinking…' : 'Recommend courses'}
        </button>
      </form>
      {generate.isPending && (
        <p className="page-status" role="status">Generating recommendations…</p>
      )}
      {error && <p role="alert" className="form-error">{error}</p>}
      {result && (
        <section aria-live="polite">
          <ol className="card-list">
            {result.items.map((item) => (
              <li key={item.course_code} className="course-card">
                <h2>{item.course_code}</h2>
                <p>{item.reason}</p>
                <p className={`prereq-badge prereq-${item.prereq_status}`}>
                  Prerequisites: {item.prereq_status.replace('_', ' ')}
                </p>
              </li>
            ))}
          </ol>
          <p className="page-status">{result.disclaimer}</p>
        </section>
      )}
    </main>
  )
}
