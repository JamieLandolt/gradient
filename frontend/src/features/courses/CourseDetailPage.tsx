import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import type { FormEvent } from 'react'
import { useParams } from 'react-router-dom'

import { ApiError, apiClient } from '../../lib/apiClient'
import type { RequiredMarks, Standing } from '../../types/api'

const STATUS_LABELS: Record<RequiredMarks['status'], string> = {
  reachable: 'Reachable',
  already_secured: 'Already secured',
  not_reachable: 'Not reachable',
  locked: 'All assessment complete — grade locked',
}

function MarkRow({
  enrolmentId,
  item,
  onSaved,
}: {
  enrolmentId: number
  item: Standing['items'][number]
  onSaved: () => void
}) {
  const [score, setScore] = useState(item.score === null ? '' : String(item.score))
  const save = useMutation({
    mutationFn: (value: number) =>
      apiClient.put(`/enrolments/${enrolmentId}/grades`, {
        [item.source === 'profile' ? 'assessment_id' : 'custom_assessment_id']: item.id,
        score: value,
      }),
    onSuccess: onSaved,
  })

  return (
    <tr>
      <th scope="row">
        {item.name}
        {item.hurdle_min_percent !== null && (
          <span className="hurdle-tag" title={item.hurdle_description ?? undefined}>
            hurdle ≥{item.hurdle_min_percent}%
          </span>
        )}
      </th>
      <td>{item.weight}%</td>
      <td>{item.due_date ?? '—'}</td>
      <td>
        <input
          aria-label={`${item.name} score`}
          type="number"
          min="0"
          max={item.max_mark}
          value={score}
          onChange={(e) => setScore(e.target.value)}
        />{' '}
        / {item.max_mark}
      </td>
      <td>
        <button
          type="button"
          disabled={score === '' || save.isPending}
          onClick={() => save.mutate(Number(score))}
        >
          {save.isPending ? 'Saving…' : 'Save'}
        </button>
        {save.isError && (
          <span role="alert" className="form-error">
            {save.error instanceof ApiError ? save.error.message : 'Failed'}
          </span>
        )}
      </td>
    </tr>
  )
}

function AddCustomAssessment({
  enrolmentId,
  onDone,
}: {
  enrolmentId: number
  onDone: () => void
}) {
  const [name, setName] = useState('')
  const [weight, setWeight] = useState('')
  const [error, setError] = useState<string | null>(null)
  const create = useMutation({
    mutationFn: () =>
      apiClient.post(`/enrolments/${enrolmentId}/assessments`, {
        name,
        weight: Number(weight),
      }),
    onSuccess: () => {
      setName('')
      setWeight('')
      setError(null)
      onDone()
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : 'Failed to add item'),
  })

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    create.mutate()
  }

  return (
    <form onSubmit={handleSubmit} className="inline-form" aria-label="Add assessment item">
      <input
        aria-label="Assessment name"
        placeholder="e.g. Final Exam"
        value={name}
        onChange={(e) => setName(e.target.value)}
        required
      />
      <input
        aria-label="Weight percent"
        placeholder="Weight %"
        type="number"
        min="0"
        max="100"
        value={weight}
        onChange={(e) => setWeight(e.target.value)}
        required
      />
      <button type="submit" disabled={create.isPending}>Add item</button>
      {error && <p role="alert" className="form-error">{error}</p>}
    </form>
  )
}

function TargetCalculator({ enrolmentId }: { enrolmentId: number }) {
  const [targetGrade, setTargetGrade] = useState(4)
  const [result, setResult] = useState<RequiredMarks | null>(null)
  const [error, setError] = useState<string | null>(null)
  const compute = useMutation({
    mutationFn: () =>
      apiClient.post<RequiredMarks>(`/enrolments/${enrolmentId}/required-marks`, {
        target_grade: targetGrade,
      }),
    onSuccess: (data) => {
      setResult(data)
      setError(null)
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : 'Failed to calculate'),
  })

  return (
    <section className="target-calculator">
      <h2>What do I need?</h2>
      <div className="calculator-actions">
        <label>
          Target grade{' '}
          <select value={targetGrade} onChange={(e) => setTargetGrade(Number(e.target.value))}>
            {[4, 5, 6, 7].map((grade) => (
              <option key={grade} value={grade}>{grade}</option>
            ))}
          </select>
        </label>
        <button type="button" onClick={() => compute.mutate()} disabled={compute.isPending}>
          {compute.isPending ? 'Calculating…' : 'Calculate'}
        </button>
      </div>
      {error && <p role="alert" className="form-error">{error}</p>}
      {result && (
        <div className={`result-card status-${result.status}`} aria-live="polite">
          <h3>{STATUS_LABELS[result.status]}</h3>
          {result.status === 'reachable' && result.required_average_percent !== null && (
            <p>
              Average needed on remaining assessment:{' '}
              <strong>{result.required_average_percent.toFixed(1)}%</strong>
            </p>
          )}
          {result.status === 'locked' && result.final_grade !== null && (
            <p>
              Final result: {result.final_percent?.toFixed(1)}% — grade{' '}
              <strong>{result.final_grade}</strong>
            </p>
          )}
          {result.per_item.length > 0 && result.status === 'reachable' && (
            <ul>
              {result.per_item.map((row) => (
                <li key={row.name}>
                  {row.name}: at least {row.required_percent.toFixed(1)}%
                </li>
              ))}
            </ul>
          )}
          {result.hurdle_warnings.map((warning) => (
            <p key={warning} role="alert" className="hurdle-warning">⚠ {warning}</p>
          ))}
        </div>
      )}
    </section>
  )
}

export function CourseDetailPage() {
  const params = useParams()
  const enrolmentId = Number(params.enrolmentId)
  const queryClient = useQueryClient()

  const { data: standing, isLoading, error } = useQuery({
    queryKey: ['standing', enrolmentId],
    queryFn: () => apiClient.get<Standing>(`/enrolments/${enrolmentId}/standing`),
    retry: false,
  })

  const refresh = () =>
    void queryClient.invalidateQueries({ queryKey: ['standing', enrolmentId] })

  if (isLoading) return <p className="page-status">Loading course…</p>

  if (error) {
    const message = error instanceof ApiError ? error.message : 'Failed to load'
    const needsItems = error instanceof ApiError && error.status === 422
    return (
      <main>
        <h1>Course</h1>
        <p className="page-status">{message}</p>
        {needsItems && <AddCustomAssessment enrolmentId={enrolmentId} onDone={refresh} />}
      </main>
    )
  }
  if (!standing) return null

  return (
    <main>
      <h1>Course standing</h1>
      <section className="standing-summary" aria-label="Standing">
        <p>
          Secured: <strong>{standing.secured_percent.toFixed(1)}%</strong> · Best case:{' '}
          {standing.best_case_percent.toFixed(1)}% · Worst case:{' '}
          {standing.worst_case_percent.toFixed(1)}%
        </p>
        {standing.projected_grade !== null && (
          <p>
            Projected: {standing.projected_percent?.toFixed(1)}% — grade{' '}
            <strong>{standing.projected_grade}</strong>
          </p>
        )}
        {/* Explains a projected grade the weighted total alone wouldn't justify. */}
        {standing.hurdle_warnings?.map((warning) => (
          <p key={warning} role="alert" className="hurdle-warning">
            ⚠ {warning} A missed hurdle caps this course below a pass, whatever the
            weighted total says.
          </p>
        ))}
      </section>

      <div className="table-scroll">
      <table className="calculator-table">
        <thead>
          <tr>
            <th scope="col">Assessment</th>
            <th scope="col">Weight</th>
            <th scope="col">Due</th>
            <th scope="col">Your mark</th>
            <th scope="col" aria-label="Actions"></th>
          </tr>
        </thead>
        <tbody>
          {standing.items.map((item) => (
            <MarkRow
              key={`${item.source}-${item.id}`}
              enrolmentId={enrolmentId}
              item={item}
              onSaved={refresh}
            />
          ))}
        </tbody>
      </table>
      </div>
      {standing.items[0]?.source === 'custom' && (
        <AddCustomAssessment enrolmentId={enrolmentId} onDone={refresh} />
      )}

      <TargetCalculator enrolmentId={enrolmentId} />
    </main>
  )
}
