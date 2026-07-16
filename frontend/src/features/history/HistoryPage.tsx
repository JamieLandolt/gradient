import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import type { FormEvent } from 'react'

import { ApiError, apiClient } from '../../lib/apiClient'
import type { Course, EnrolmentSummary } from '../../types/api'

function TransferForm({ onDone }: { onDone: () => void }) {
  const { data: courses } = useQuery({
    queryKey: ['courses'],
    queryFn: () => apiClient.get<Course[]>('/courses'),
  })
  const [courseCode, setCourseCode] = useState('')
  const [year, setYear] = useState(2024)
  const [semester, setSemester] = useState('S1')
  const [grade, setGrade] = useState(5)
  const [error, setError] = useState<string | null>(null)

  const create = useMutation({
    mutationFn: () =>
      apiClient.post('/enrolments', {
        course_code: courseCode,
        year,
        semester,
        status: 'completed',
        is_transfer: true,
        final_grade: grade,
      }),
    onSuccess: () => {
      setError(null)
      onDone()
    },
    onError: (err) =>
      setError(err instanceof ApiError ? err.message : 'Failed to add course'),
  })

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (!courseCode) {
      setError('Pick a course')
      return
    }
    create.mutate()
  }

  return (
    <form onSubmit={handleSubmit} className="inline-form" aria-label="Add past course">
      <select
        aria-label="Course"
        value={courseCode}
        onChange={(e) => setCourseCode(e.target.value)}
      >
        <option value="">Choose a course…</option>
        {(courses ?? []).map((course) => (
          <option key={course.code} value={course.code}>
            {course.code} — {course.title}
          </option>
        ))}
      </select>
      <input
        aria-label="Year completed"
        type="number"
        min="2000"
        max="2100"
        value={year}
        onChange={(e) => setYear(Number(e.target.value))}
      />
      <select
        aria-label="Semester completed"
        value={semester}
        onChange={(e) => setSemester(e.target.value)}
      >
        <option value="S1">S1</option>
        <option value="S2">S2</option>
        <option value="SUMMER">Summer</option>
      </select>
      <label>
        Final grade{' '}
        <select
          aria-label="Final grade"
          value={grade}
          onChange={(e) => setGrade(Number(e.target.value))}
        >
          {[1, 2, 3, 4, 5, 6, 7].map((g) => (
            <option key={g} value={g}>{g}</option>
          ))}
        </select>
      </label>
      <button type="submit" disabled={create.isPending}>
        {create.isPending ? 'Adding…' : 'Add past course'}
      </button>
      {error && <p role="alert" className="form-error">{error}</p>}
    </form>
  )
}

export function HistoryPage() {
  const queryClient = useQueryClient()
  const { data: history, isLoading } = useQuery({
    queryKey: ['history'],
    queryFn: () => apiClient.get<EnrolmentSummary[]>('/me/history'),
  })

  const completed = (history ?? []).filter((e) => e.status === 'completed')
  const current = (history ?? []).filter((e) => e.status !== 'completed')

  return (
    <main>
      <h1>Course history</h1>
      <p>
        Record courses you completed before using Gradient — they feed prerequisite
        checking, your GPA, and recommendations.
      </p>
      <TransferForm
        onDone={() => {
          void queryClient.invalidateQueries({ queryKey: ['history'] })
          void queryClient.invalidateQueries({ queryKey: ['gpa'] })
        }}
      />

      {isLoading && <p className="page-status">Loading history…</p>}

      <h2>Completed</h2>
      {completed.length === 0 && <p className="page-status">Nothing completed yet.</p>}
      <table className="calculator-table">
        <tbody>
          {completed.map((row) => (
            <tr key={row.enrolment_id}>
              <th scope="row">{row.course_code}</th>
              <td>{row.course_title}</td>
              <td>
                {row.year} {row.semester}
                {row.is_transfer && ' (transfer)'}
              </td>
              <td>Grade {row.final_grade ?? '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <h2>In progress / planned</h2>
      {current.length === 0 && <p className="page-status">No current courses.</p>}
      <ul className="card-list">
        {current.map((row) => (
          <li key={row.enrolment_id} className="course-card">
            <h3>{row.course_code}</h3>
            <p>{row.course_title}</p>
            <p className="page-status">
              {row.year} {row.semester}
            </p>
            <span className={`status-badge status-${row.status}`}>
              {row.status.replace('_', ' ')}
            </span>
          </li>
        ))}
      </ul>
    </main>
  )
}
