import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import { ApiError, apiClient } from '../../lib/apiClient'
import type {
  DegreePlanSummary,
  PlanSequence,
  PrereqStatusRow,
  Program,
  SavedDegreePlan,
  UserProgramLink,
} from '../../types/api'

const PREREQ_LABELS: Record<PrereqStatusRow['prereq_status'], string> = {
  met: 'Prerequisites met',
  partially_met: 'Partially met',
  not_met: 'Not met',
}

type PlanLike = Pick<PlanSequence, 'feasible' | 'semesters' | 'diagnostics'>

function PlanView({ plan }: { plan: PlanLike }) {
  return (
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
                <li key={entry.course_code}>
                  {entry.course_code} ({entry.units} units)
                  {entry.explanation && (
                    <span className="entry-explanation">{entry.explanation}</span>
                  )}
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </div>
  )
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
  const queryClient = useQueryClient()
  const [startYear, setStartYear] = useState(2026)
  const [startSemester, setStartSemester] = useState<'S1' | 'S2'>('S2')
  const [prioritiseAvailable, setPrioritiseAvailable] = useState(false)
  const [interests, setInterests] = useState('')
  const [planName, setPlanName] = useState('My plan')
  const [plan, setPlan] = useState<PlanSequence | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)

  function requestBody() {
    return {
      start_year: startYear,
      start_semester: startSemester,
      prioritise_available: prioritiseAvailable,
      interests: interests
        .split(',')
        .map((term) => term.trim())
        .filter(Boolean),
    }
  }

  const generate = useMutation({
    mutationFn: () => apiClient.post<PlanSequence>('/planner/sequence', requestBody()),
    onSuccess: (data) => {
      setPlan(data)
      setError(null)
      setSaved(false)
    },
    onError: (err) =>
      setError(err instanceof ApiError ? err.message : 'Could not build a plan'),
  })

  const savePlan = useMutation({
    mutationFn: () =>
      apiClient.post<SavedDegreePlan>('/planner/plans', {
        ...requestBody(),
        name: planName.trim() || 'My plan',
      }),
    onSuccess: () => {
      setSaved(true)
      void queryClient.invalidateQueries({ queryKey: ['saved-plans'] })
    },
    onError: (err) =>
      setError(err instanceof ApiError ? err.message : 'Could not save the plan'),
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

      <div className="pref-row">
        <label>
          <input
            type="checkbox"
            checked={prioritiseAvailable}
            onChange={(e) => setPrioritiseAvailable(e.target.checked)}
          />{' '}
          Prioritise courses I can take now
        </label>
        <input
          aria-label="Topic interests"
          placeholder="Interests, e.g. algorithms, security"
          value={interests}
          onChange={(e) => setInterests(e.target.value)}
        />
      </div>

      {error && <p role="alert" className="form-error">{error}</p>}

      {plan && (
        <>
          <PlanView plan={plan} />
          <div className="pref-row">
            <input
              aria-label="Plan name"
              value={planName}
              onChange={(e) => {
                setPlanName(e.target.value)
                setSaved(false)
              }}
            />
            <button type="button" onClick={() => savePlan.mutate()} disabled={savePlan.isPending}>
              {savePlan.isPending ? 'Saving…' : 'Save this plan'}
            </button>
            {saved && <span className="page-status">Saved ✓</span>}
          </div>
        </>
      )}
    </section>
  )
}

function SavedPlans() {
  const queryClient = useQueryClient()
  const { data: plans } = useQuery({
    queryKey: ['saved-plans'],
    queryFn: () => apiClient.get<DegreePlanSummary[]>('/planner/plans'),
  })
  const [openId, setOpenId] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)

  // A read modelled as a query: retries on a transient failure, caches per plan
  // (instant re-open), and gives loading/error states — unlike the previous
  // useMutation, which failed silently and rendered nothing on any hiccup.
  const openPlan = useQuery({
    queryKey: ['saved-plan', openId],
    queryFn: () => apiClient.get<SavedDegreePlan>(`/planner/plans/${openId}`),
    enabled: openId !== null,
  })

  const remove = useMutation({
    mutationFn: (id: number) => apiClient.delete(`/planner/plans/${id}`),
    onSuccess: (_data, id) => {
      if (openId === id) setOpenId(null)
      void queryClient.invalidateQueries({ queryKey: ['saved-plans'] })
    },
    onError: (err) =>
      setError(err instanceof ApiError ? err.message : 'Could not delete that plan'),
  })

  if (!plans || plans.length === 0) return null

  return (
    <section aria-label="Saved plans">
      <h2>Saved plans</h2>
      {error && <p role="alert" className="form-error">{error}</p>}
      <ul className="card-list">
        {plans.map((summary) => (
          <li key={summary.id} className="course-card">
            <div className="saved-plan-row">
              <strong>{summary.name}</strong>
              <span className={`prereq-badge prereq-${summary.feasible ? 'met' : 'not_met'}`}>
                {summary.feasible ? 'Feasible' : 'Not feasible'}
              </span>
              <button
                type="button"
                aria-pressed={openId === summary.id}
                onClick={() => setOpenId(openId === summary.id ? null : summary.id)}
              >
                {openId === summary.id ? 'Hide' : 'View'}
              </button>
              <button
                type="button"
                className="link-button"
                onClick={() => remove.mutate(summary.id)}
                disabled={remove.isPending}
              >
                Delete
              </button>
            </div>
            {openId === summary.id && (
              <div aria-live="polite">
                {openPlan.isFetching && (
                  <p className="page-status" role="status">Loading plan…</p>
                )}
                {openPlan.error && (
                  <p role="alert" className="form-error">
                    {openPlan.error instanceof ApiError
                      ? openPlan.error.message
                      : 'Could not open that plan'}
                  </p>
                )}
                {openPlan.data && <PlanView plan={openPlan.data} />}
              </div>
            )}
          </li>
        ))}
      </ul>
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
      <SavedPlans />
    </main>
  )
}
