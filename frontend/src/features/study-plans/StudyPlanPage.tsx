import { useMutation, useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import type { FormEvent } from 'react'

import { ApiError, apiClient } from '../../lib/apiClient'
import type { EnrolmentSummary, StudyPlan } from '../../types/api'

export function StudyPlanPage() {
  const { data: enrolments } = useQuery({
    queryKey: ['enrolments'],
    queryFn: () => apiClient.get<EnrolmentSummary[]>('/enrolments'),
  })
  const [enrolmentId, setEnrolmentId] = useState('')
  const [targetGrade, setTargetGrade] = useState(5)
  const [plan, setPlan] = useState<StudyPlan | null>(null)
  const [error, setError] = useState<string | null>(null)

  const generate = useMutation({
    mutationFn: () =>
      apiClient.post<StudyPlan>('/study-plans/generate', {
        enrolment_id: Number(enrolmentId),
        target_grade: targetGrade,
      }),
    onSuccess: (data) => {
      setPlan(data)
      setError(null)
    },
    onError: (err) =>
      setError(err instanceof ApiError ? err.message : 'Could not generate a plan'),
  })

  const current = (enrolments ?? []).filter((e) => e.status === 'in_progress')

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (!enrolmentId) {
      setError('Pick a course')
      return
    }
    generate.mutate()
  }

  return (
    <main>
      <h1>Study plan</h1>
      <p>Generate a session-by-session study schedule for a course's remaining assessment.</p>
      <form onSubmit={handleSubmit} className="inline-form">
        <select
          aria-label="Course"
          value={enrolmentId}
          onChange={(e) => setEnrolmentId(e.target.value)}
        >
          <option value="">Choose a course…</option>
          {current.map((enrolment) => (
            <option key={enrolment.enrolment_id} value={enrolment.enrolment_id}>
              {enrolment.course_code} ({enrolment.year} {enrolment.semester})
            </option>
          ))}
        </select>
        <label>
          Target grade{' '}
          <select
            aria-label="Target grade"
            value={targetGrade}
            onChange={(e) => setTargetGrade(Number(e.target.value))}
          >
            {[4, 5, 6, 7].map((grade) => (
              <option key={grade} value={grade}>{grade}</option>
            ))}
          </select>
        </label>
        <button type="submit" disabled={generate.isPending}>
          {generate.isPending ? 'Generating…' : 'Generate plan'}
        </button>
      </form>
      {generate.isPending && <p className="page-status" role="status">Building your plan…</p>}
      {error && <p role="alert" className="form-error">{error}</p>}
      {plan && (
        <section aria-live="polite">
          <h2>
            {plan.course_code} — aiming for grade {plan.target_grade}
            {plan.required_average_percent !== null &&
              ` (needs ${plan.required_average_percent.toFixed(0)}% average)`}
          </h2>
          <ul className="session-list">
            {plan.sessions.map((session, index) => (
              <li key={index}>
                <strong>{session.session_date}</strong> · {session.duration_minutes} min —{' '}
                {session.focus}
              </li>
            ))}
          </ul>
          <p className="page-status">{plan.disclaimer}</p>
        </section>
      )}
    </main>
  )
}
