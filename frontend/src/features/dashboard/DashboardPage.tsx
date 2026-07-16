import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link } from 'react-router-dom'

import { CourseSearchSelect } from '../../components/CourseSearchSelect'
import { ApiError, apiClient } from '../../lib/apiClient'
import type { Course, EnrolmentSummary, GpaSummary } from '../../types/api'

const CURRENT_YEAR = 2026

// Decorative ascending "grade curve" used until enough real grades exist.
const MOTIF_BARS = [3, 4, 3.5, 5, 7]
const MAX_GRADE = 7

function GradeBadge({ grade }: { grade: number | null }) {
  if (grade === null) return null
  const tone = grade >= 5 ? 'ok' : grade >= 4 ? 'warn' : 'danger'
  return <span className={`grade-badge grade-${tone}`}>Grade {grade}</span>
}

interface UserProgramRow {
  position: number
  programs: { id: number; code: string; title: string; total_units: number }
}

function GpaStatCard({
  gpa,
  completedGrades,
}: {
  gpa: GpaSummary
  completedGrades: number[]
}) {
  const { data: userPrograms } = useQuery({
    queryKey: ['planner-programs'],
    queryFn: () => apiClient.get<UserProgramRow[]>('/planner/programs'),
  })
  const targetUnits = (userPrograms ?? []).reduce(
    (sum, row) => sum + row.programs.total_units,
    0,
  )
  const bars =
    completedGrades.length >= 2
      ? [...completedGrades].sort((a, b) => a - b).slice(-5)
      : MOTIF_BARS

  return (
    <section className="stat-card" aria-label="GPA summary">
      <div className="stat-card-head">
        <div className="stat-block">
          <span className="stat-label">Cumulative GPA</span>
          <span className="stat-value">{gpa.gpa === null ? '—' : gpa.gpa.toFixed(2)}</span>
        </div>
        <div className="stat-block right">
          <span className="stat-label">Units</span>
          <span className="stat-value-sm">
            {gpa.total_units}
            {targetUnits > 0 ? `/${targetUnits}` : ''}
          </span>
        </div>
      </div>
      <div className="rise-bars" aria-hidden="true">
        {bars.map((height, index) => (
          <span key={index} style={{ height: `${(height / MAX_GRADE) * 100}%` }} />
        ))}
      </div>
    </section>
  )
}

function AddCourseForm({ onDone }: { onDone: () => void }) {
  const { data: courses } = useQuery({
    queryKey: ['courses'],
    queryFn: () => apiClient.get<Course[]>('/courses'),
  })
  const [courseCode, setCourseCode] = useState('')
  const [semester, setSemester] = useState('S1')
  const [year, setYear] = useState(CURRENT_YEAR)
  const [status, setStatus] = useState('in_progress')
  const [error, setError] = useState<string | null>(null)

  const create = useMutation({
    mutationFn: (payload: object) => apiClient.post('/enrolments', payload),
    onSuccess: () => {
      setError(null)
      onDone()
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : 'Failed to add course'),
  })

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (!courseCode) {
      setError('Pick a course')
      return
    }
    create.mutate({ course_code: courseCode, year, semester, status })
  }

  return (
    <form onSubmit={handleSubmit} className="inline-form" aria-label="Add course">
      <CourseSearchSelect
        id="dashboard-course"
        courses={courses ?? []}
        value={courseCode}
        onChange={setCourseCode}
      />
      <input
        aria-label="Year"
        type="number"
        min="2000"
        max="2100"
        value={year}
        onChange={(e) => setYear(Number(e.target.value))}
      />
      <select aria-label="Semester" value={semester} onChange={(e) => setSemester(e.target.value)}>
        <option value="S1">S1</option>
        <option value="S2">S2</option>
        <option value="SUMMER">Summer</option>
      </select>
      <select aria-label="Status" value={status} onChange={(e) => setStatus(e.target.value)}>
        <option value="in_progress">In progress</option>
        <option value="planned">Planned</option>
        <option value="completed">Completed</option>
      </select>
      <button type="submit" disabled={create.isPending}>
        {create.isPending ? 'Adding…' : 'Add course'}
      </button>
      {error && <p role="alert" className="form-error">{error}</p>}
    </form>
  )
}

export function DashboardPage() {
  const queryClient = useQueryClient()
  const { data: enrolments, isLoading } = useQuery({
    queryKey: ['enrolments'],
    queryFn: () => apiClient.get<EnrolmentSummary[]>('/enrolments'),
  })
  const { data: gpa } = useQuery({
    queryKey: ['gpa'],
    queryFn: () => apiClient.get<GpaSummary>('/me/gpa'),
  })

  const inProgress = (enrolments ?? []).filter((e) => e.status !== 'completed')
  const completedGrades = (enrolments ?? [])
    .filter((e) => e.status === 'completed' && e.final_grade !== null)
    .map((e) => e.final_grade as number)

  return (
    <main>
      {/* Heading + add-course form share the left column; the GPA card sits
          beside them (top-aligned) instead of floating in the heading row and
          leaving the search bar stranded below it. Wraps to a single column on
          narrow screens. */}
      <div className="dashboard-top">
        <div className="dashboard-top-main">
          <h1>Dashboard</h1>
          <AddCourseForm
            onDone={() => {
              void queryClient.invalidateQueries({ queryKey: ['enrolments'] })
              void queryClient.invalidateQueries({ queryKey: ['gpa'] })
            }}
          />
        </div>
        {gpa && <GpaStatCard gpa={gpa} completedGrades={completedGrades} />}
      </div>

      {isLoading && <p className="page-status">Loading your courses…</p>}
      {!isLoading && inProgress.length === 0 && (
        <p className="page-status">
          No current courses yet — add one above, or record past results in{' '}
          <Link to="/history">History</Link>.
        </p>
      )}

      <ul className="card-list">
        {inProgress.map((enrolment) => (
          <li key={enrolment.enrolment_id} className="course-card">
            <h2>
              <Link to={`/courses/${enrolment.enrolment_id}`}>
                {enrolment.course_code}
              </Link>
            </h2>
            <p>{enrolment.course_title}</p>
            <p className="page-status">
              {enrolment.year} {enrolment.semester} · {enrolment.status.replace('_', ' ')}
            </p>
            <GradeBadge grade={enrolment.final_grade} />
          </li>
        ))}
      </ul>
    </main>
  )
}
