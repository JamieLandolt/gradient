import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import { ApiError, apiClient } from '../../lib/apiClient'
import type { PlanSequence, PrereqStatusRow, Program, UserProgramLink } from '../../types/api'

const PREREQ_LABELS: Record<PrereqStatusRow['prereq_status'], string> = {
  met: 'Prerequisites met',
  partially_met: 'Partially met',
  not_met: 'Not met',
}

function ProgramPicker() {
  const queryClient = useQueryClient()
  const { data: programs } = useQuery({
    queryKey: ['programs'],
    queryFn: () => apiClient.get<Program[]>('/programs'),
  })
  const { data: mine } = useQuery({
    queryKey: ['my-programs'],
    queryFn: () => apiClient.get<UserProgramLink[]>('/planner/programs'),
  })
  const [selected, setSelected] = useState<number[]>([])

  const save = useMutation({
    mutationFn: (programIds: number[]) =>
      apiClient.put('/planner/programs', { program_ids: programIds }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['my-programs'] })
      void queryClient.invalidateQueries({ queryKey: ['prereq-status'] })
    },
  })

  function toggle(programId: number) {
    setSelected((current) =>
      current.includes(programId)
        ? current.filter((id) => id !== programId)
        : [...current, programId].slice(-2), // at most two programs (dual degree)
    )
  }

  return (
    <section aria-label="Program selection">
      <h2>Your program(s)</h2>
      {mine && mine.length > 0 && (
        <p>
          Enrolled: {mine.map((link) => link.programs.code).join(' + ')}
          {mine.length === 2 && ' (dual degree)'}
        </p>
      )}
      <div className="calculator-actions">
        {(programs ?? []).map((program) => (
          <label key={program.id}>
            <input
              type="checkbox"
              checked={selected.includes(program.id)}
              onChange={() => toggle(program.id)}
            />{' '}
            {program.code} — {program.title}
          </label>
        ))}
        <button
          type="button"
          disabled={selected.length === 0 || save.isPending}
          onClick={() => save.mutate(selected)}
        >
          {save.isPending ? 'Saving…' : 'Set programs'}
        </button>
      </div>
    </section>
  )
}

function PrereqStatusList() {
  const { data: statuses, error } = useQuery({
    queryKey: ['prereq-status'],
    queryFn: () => apiClient.get<PrereqStatusRow[]>('/planner/prereq-status'),
    retry: false,
  })

  if (error) {
    return (
      <p className="page-status">
        {error instanceof ApiError ? error.message : 'Could not load prerequisite status'}
      </p>
    )
  }
  if (!statuses) return null

  return (
    <section aria-label="Prerequisite status">
      <h2>Prerequisite status</h2>
      <ul className="card-list">
        {statuses.map((row) => (
          <li key={row.course_code} className={`course-card prereq-${row.prereq_status}`}>
            <h3>{row.course_code}</h3>
            <p>{row.course_title}</p>
            {row.is_completed ? (
              <p className="prereq-badge prereq-met">Completed ✓</p>
            ) : (
              <p className={`prereq-badge prereq-${row.prereq_status}`}>
                {PREREQ_LABELS[row.prereq_status]}
                {row.outstanding.length > 0 && ` — needs ${row.outstanding.join(' or ')}`}
              </p>
            )}
            {row.requires_manual_check && (
              <p className="hurdle-warning">Check the course profile manually.</p>
            )}
          </li>
        ))}
      </ul>
    </section>
  )
}

function SequencePlanner() {
  const [startYear, setStartYear] = useState(2026)
  const [startSemester, setStartSemester] = useState<'S1' | 'S2'>('S2')
  const [plan, setPlan] = useState<PlanSequence | null>(null)
  const [error, setError] = useState<string | null>(null)

  const generate = useMutation({
    mutationFn: () =>
      apiClient.post<PlanSequence>('/planner/sequence', {
        start_year: startYear,
        start_semester: startSemester,
      }),
    onSuccess: (data) => {
      setPlan(data)
      setError(null)
    },
    onError: (err) =>
      setError(err instanceof ApiError ? err.message : 'Could not build a plan'),
  })

  return (
    <section aria-label="Study sequence">
      <h2>Suggested study sequence</h2>
      <div className="calculator-actions">
        <label>
          Starting{' '}
          <input
            aria-label="Start year"
            type="number"
            min="2024"
            max="2035"
            value={startYear}
            onChange={(e) => setStartYear(Number(e.target.value))}
          />
        </label>
        <select
          aria-label="Start semester"
          value={startSemester}
          onChange={(e) => setStartSemester(e.target.value as 'S1' | 'S2')}
        >
          <option value="S1">S1</option>
          <option value="S2">S2</option>
        </select>
        <button type="button" onClick={() => generate.mutate()} disabled={generate.isPending}>
          {generate.isPending ? 'Planning…' : 'Generate plan'}
        </button>
      </div>
      {error && <p role="alert" className="form-error">{error}</p>}
      {plan && (
        <div aria-live="polite">
          {!plan.feasible && (
            <p role="alert" className="form-error">
              This plan is not feasible — see the issues below.
            </p>
          )}
          {plan.diagnostics.map((diagnostic) => (
            <p
              key={diagnostic.message}
              className={diagnostic.severity === 'error' ? 'form-error' : 'hurdle-warning'}
            >
              {diagnostic.message}
            </p>
          ))}
          <div className="semester-grid">
            {plan.semesters.map((semester) => (
              <div key={semester.label} className="semester-column">
                <h3>{semester.label}</h3>
                {semester.entries.length === 0 && <p className="page-status">—</p>}
                <ul>
                  {semester.entries.map((entry) => (
                    <li key={entry.course_code} title={entry.explanation}>
                      {entry.course_code} ({entry.units} units)
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  )
}

export function PlannerPage() {
  return (
    <main>
      <h1>Degree planner</h1>
      <ProgramPicker />
      <PrereqStatusList />
      <SequencePlanner />
    </main>
  )
}
