import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import type { FormEvent } from 'react'

import { ApiError, apiClient } from '../../lib/apiClient'

interface IngestionJob {
  id: number
  status: string
  course_code: string
  profile_version_id: number | null
  cached?: boolean
  warnings?: string[]
}

interface DraftVersion {
  id: number
  version_label: string
  status: string
  extraction_provider: string
  courses: { code: string; title: string }
}

function CuratorQueue() {
  const queryClient = useQueryClient()
  const { data: drafts, error } = useQuery({
    queryKey: ['draft-versions'],
    queryFn: () => apiClient.get<DraftVersion[]>('/curator/profile-versions'),
    retry: false,
  })
  const act = useMutation({
    mutationFn: ({ id, action }: { id: number; action: 'verify' | 'reject' }) =>
      apiClient.post(`/curator/profile-versions/${id}/${action}`),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['draft-versions'] }),
  })

  if (error) {
    // Students get 403 here — the queue is curator-only.
    return null
  }
  if (!drafts) return null

  return (
    <section aria-label="Curator review queue">
      <h2>Curator review queue</h2>
      {drafts.length === 0 && <p className="page-status">No drafts awaiting review.</p>}
      <ul className="card-list">
        {drafts.map((draft) => (
          <li key={draft.id} className="course-card">
            <h3>
              {draft.courses.code} — {draft.version_label}
            </h3>
            <p className="page-status">
              extracted by {draft.extraction_provider} · unverified
            </p>
            <div className="calculator-actions">
              <button
                type="button"
                onClick={() => act.mutate({ id: draft.id, action: 'verify' })}
              >
                Verify
              </button>
              <button
                type="button"
                onClick={() => act.mutate({ id: draft.id, action: 'reject' })}
              >
                Reject
              </button>
            </div>
          </li>
        ))}
      </ul>
    </section>
  )
}

export function ImportPage() {
  const [payload, setPayload] = useState('')
  const [job, setJob] = useState<IngestionJob | null>(null)
  const [error, setError] = useState<string | null>(null)

  const submit = useMutation({
    mutationFn: () =>
      apiClient.post<IngestionJob>('/ingestion/jobs', {
        source_type: 'text',
        payload,
      }),
    onSuccess: (data) => {
      setJob(data)
      setError(null)
    },
    onError: (err) =>
      setError(err instanceof ApiError ? err.message : 'Extraction failed'),
  })

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    submit.mutate()
  }

  return (
    <main>
      <h1>Import a course profile</h1>
      <p>
        Paste the text of a course profile (ECP). Gradient extracts the assessment
        items, weights, hurdles, grade cut-offs, and prerequisites — a curator then
        verifies them before they drive anyone's projections.
      </p>
      <form onSubmit={handleSubmit}>
        <textarea
          aria-label="Course profile text"
          rows={12}
          value={payload}
          onChange={(e) => setPayload(e.target.value)}
          placeholder={'Course code: COMP2140\nCourse title: …\nAssessment:\n- …'}
          required
        />
        <button type="submit" disabled={submit.isPending}>
          {submit.isPending ? 'Extracting…' : 'Extract'}
        </button>
      </form>
      {error && <p role="alert" className="form-error">{error}</p>}
      {job && (
        <section className="result-card" aria-live="polite">
          <h2>
            {job.course_code}: {job.cached ? 'already extracted (cached)' : 'extracted'}
          </h2>
          <p className="page-status">
            Status: {job.status} — awaiting curator verification before it is used for
            grade projections.
          </p>
          {(job.warnings ?? []).map((warning) => (
            <p key={warning} className="hurdle-warning">⚠ {warning}</p>
          ))}
        </section>
      )}
      <CuratorQueue />
    </main>
  )
}
