import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import type { ChangeEvent, FormEvent } from 'react'

import { ApiError, apiClient } from '../../lib/apiClient'

interface IngestionJob {
  id: number
  status: 'queued' | 'extracted' | 'failed'
  course_code: string
  profile_version_id: number | null
  error?: string
}

const TERMINAL: ReadonlySet<string> = new Set(['extracted', 'failed'])
const POLL_INTERVAL_MS = 1500
// Stop polling after this long so a job wedged in 'queued' (e.g. the worker was
// killed mid-extraction, and nothing on the backend reaps it) surfaces a
// recoverable timeout instead of spinning on "Extracting…" forever.
const MAX_POLL_MS = 90_000

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
  const queryClient = useQueryClient()
  const [payload, setPayload] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [courseCode, setCourseCode] = useState('')
  const [jobId, setJobId] = useState<number | null>(null)
  const [timedOut, setTimedOut] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const submit = useMutation({
    mutationFn: () => {
      if (courseCode.trim()) {
        return apiClient.post<IngestionJob>('/ingestion/from-url', {
          course_code: courseCode.trim(),
        })
      }
      if (file) {
        const form = new FormData()
        form.append('file', file)
        return apiClient.postForm<IngestionJob>('/ingestion/uploads', form)
      }
      return apiClient.post<IngestionJob>('/ingestion/jobs', {
        source_type: 'text',
        payload,
      })
    },
    onSuccess: (data) => {
      setJobId(data.id)
      setTimedOut(false)
      setError(null)
    },
    onError: (err) =>
      setError(err instanceof ApiError ? err.message : 'Could not submit the profile'),
  })

  // Poll the queued job until extraction finishes in the background (FR-3.5.3),
  // but stop once we hit the deadline (see MAX_POLL_MS) so the UI can recover.
  const { data: job, error: pollError } = useQuery({
    queryKey: ['ingestion-job', jobId],
    queryFn: () => apiClient.get<IngestionJob>(`/ingestion/jobs/${jobId}`),
    enabled: jobId !== null && !timedOut,
    refetchInterval: (query) =>
      TERMINAL.has(query.state.data?.status ?? '') ? false : POLL_INTERVAL_MS,
  })

  // Arm a deadline when a new job starts; if it fires before a terminal status,
  // stop polling and show a timeout the user can retry from.
  useEffect(() => {
    if (jobId === null) return
    const timer = setTimeout(() => setTimedOut(true), MAX_POLL_MS)
    return () => clearTimeout(timer)
  }, [jobId])

  // When a job reaches a terminal state, refresh the curator queue so a newly
  // drafted version shows up without a manual reload.
  useEffect(() => {
    if (job && TERMINAL.has(job.status)) {
      void queryClient.invalidateQueries({ queryKey: ['draft-versions'] })
    }
  }, [job, queryClient])

  function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    setFile(event.target.files?.[0] ?? null)
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    submit.mutate()
  }

  const isPolling = job?.status === 'queued' && !timedOut
  const isWaiting = submit.isPending || isPolling
  const canSubmit = file !== null || payload.trim().length > 0 || courseCode.trim().length > 0
  const pasteOrUploadDisabled = courseCode.trim().length > 0
  const courseCodeDisabled = file !== null || payload.trim().length > 0

  return (
    <main>
      <h1>Import a course profile</h1>
      <p>
        Enter a UQ course code to fetch its current profile automatically, upload a course
        profile (ECP) as a PDF, or paste its text. Gradient extracts the assessment items,
        weights, hurdles, grade cut-offs, and prerequisites in the background — a curator
        then verifies them before they drive anyone's projections.
      </p>
      <form onSubmit={handleSubmit}>
        <label htmlFor="ecp-course-code">Course code (fetches automatically)</label>
        <input
          id="ecp-course-code"
          value={courseCode}
          onChange={(e) => setCourseCode(e.target.value)}
          placeholder="e.g. COMP3506"
          disabled={courseCodeDisabled}
        />
        <label htmlFor="ecp-file">…or upload a PDF or .txt</label>
        <input
          id="ecp-file"
          type="file"
          accept=".pdf,.txt,application/pdf,text/plain"
          onChange={handleFileChange}
          disabled={pasteOrUploadDisabled}
        />
        <textarea
          aria-label="Course profile text"
          rows={12}
          value={payload}
          onChange={(e) => setPayload(e.target.value)}
          placeholder={'…or paste:\nCourse code: COMP2140\nCourse title: …\nAssessment:\n- …'}
          disabled={file !== null || pasteOrUploadDisabled}
        />
        <button type="submit" disabled={!canSubmit || isWaiting}>
          {isWaiting ? 'Extracting…' : 'Extract'}
        </button>
      </form>
      {error && <p role="alert" className="form-error">{error}</p>}
      {/* A failed poll used to leave `job` undefined, so the whole status panel
          vanished and the button read "Extract" again — a submitted job looked
          like nothing had happened. Say so instead; a later poll may recover. */}
      {jobId !== null && !job && pollError && (
        <p role="alert" className="form-error">
          {pollError instanceof ApiError ? pollError.message : 'Could not read the job status'}
          {' '}— your profile was submitted and may still be extracting.
        </p>
      )}
      {job && (
        <section className="result-card" aria-live="polite">
          {job.status === 'queued' && !timedOut && (
            <p className="page-status">Queued — extracting in the background…</p>
          )}
          {job.status === 'queued' && timedOut && (
            <p role="alert" className="form-error">
              This is taking longer than expected. The extraction may still finish — check the
              curator queue shortly, or try submitting again.
            </p>
          )}
          {job.status === 'extracted' && (
            <>
              <h2>{job.course_code}: extracted</h2>
              <p className="page-status">
                Awaiting curator verification before it is used for grade projections.
              </p>
            </>
          )}
          {job.status === 'failed' && (
            <p role="alert" className="form-error">
              Extraction failed: {job.error || 'the profile could not be read.'}
            </p>
          )}
        </section>
      )}
      <CuratorQueue />
    </main>
  )
}
