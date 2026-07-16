import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Fragment, useState } from 'react'
import type { FormEvent } from 'react'

import { ApiError, apiClient } from '../../lib/apiClient'
import type {
  RemainingAssessment,
  StudyAvailabilitySlot,
  WeeklyStudyBlock,
  WeeklyStudyPlan,
  WeeklyStudyPlanSummary,
} from '../../types/api'

const DAY_LABELS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
// 7am–10pm covers realistic study/class hours without a 24-row grid.
const HOURS = Array.from({ length: 16 }, (_, i) => i + 7)

function slotKey(day: number, hour: number) {
  return `${day}-${hour}`
}

function hourLabel(hour: number) {
  const period = hour < 12 ? 'am' : 'pm'
  const display = hour % 12 === 0 ? 12 : hour % 12
  return `${display}${period}`
}

/** YYYY-MM-DD in the viewer's own timezone.
 *
 * Not toISOString().slice(0,10): that converts to UTC first, so anywhere ahead
 * of UTC the date rolls back a day — a Brisbane student opening this before
 * 10am got the Sunday, labelled "Monday", and generated a plan for the wrong
 * week (keyed unique on week_start, so they could end up with two plans for one
 * real week).
 */
function toLocalIsoDate(value: Date): string {
  const month = String(value.getMonth() + 1).padStart(2, '0')
  const day = String(value.getDate()).padStart(2, '0')
  return `${value.getFullYear()}-${month}-${day}`
}

function currentWeekMonday(): string {
  const now = new Date()
  const day = now.getDay() // 0=Sun..6=Sat
  const diffToMonday = day === 0 ? -6 : 1 - day
  const monday = new Date(now)
  monday.setDate(now.getDate() + diffToMonday)
  return toLocalIsoDate(monday)
}

function WeekGrid({
  cellClass,
  cellContent,
  onCellClick,
}: {
  cellClass: (day: number, hour: number) => string
  cellContent?: (day: number, hour: number) => React.ReactNode
  onCellClick?: (day: number, hour: number) => void
}) {
  return (
    <div className="week-grid" role="grid">
      <div />
      {DAY_LABELS.map((label) => (
        <div key={label} className="week-grid-header">{label}</div>
      ))}
      {HOURS.map((hour) => (
        <Fragment key={hour}>
          <div className="week-grid-hour-label">{hourLabel(hour)}</div>
          {DAY_LABELS.map((label, day) => (
            <button
              key={label}
              type="button"
              className={`week-slot ${cellClass(day, hour)}`}
              onClick={onCellClick ? () => onCellClick(day, hour) : undefined}
              disabled={!onCellClick}
              aria-label={`${label} ${hourLabel(hour)}`}
            >
              {cellContent?.(day, hour)}
            </button>
          ))}
        </Fragment>
      ))}
    </div>
  )
}

type SlotMap = Record<string, 'blocked' | 'study'>

function serverSlots(rows: StudyAvailabilitySlot[] | undefined): SlotMap {
  const map: SlotMap = {}
  for (const row of rows ?? []) map[slotKey(row.day_of_week, row.start_hour)] = row.slot_type
  return map
}

function AvailabilityEditor() {
  const queryClient = useQueryClient()
  const { data, isLoading, error: loadError } = useQuery({
    queryKey: ['study-availability'],
    queryFn: () => apiClient.get<StudyAvailabilitySlot[]>('/study-availability'),
  })
  const [pending, setPending] = useState<SlotMap | null>(null)
  const [error, setError] = useState<string | null>(null)

  const slots = pending ?? serverSlots(data)

  function cycle(day: number, hour: number) {
    const key = slotKey(day, hour)
    // Functional update: two clicks landing in one render batch would otherwise
    // both read the same `slots` snapshot, and the earlier one would be lost.
    setPending((prev) => {
      const next = { ...(prev ?? serverSlots(data)) }
      const current = next[key]
      if (current === undefined) next[key] = 'study'
      else if (current === 'study') next[key] = 'blocked'
      else delete next[key]
      return next
    })
  }

  const save = useMutation({
    mutationFn: () =>
      apiClient.put<StudyAvailabilitySlot[]>('/study-availability', {
        slots: Object.entries(slots).map(([key, slot_type]) => {
          const [day, hour] = key.split('-').map(Number)
          return { day_of_week: day, start_hour: hour, slot_type }
        }),
      }),
    onSuccess: async () => {
      setError(null)
      // Wait for the refetch before dropping the local edits, otherwise the grid
      // re-derives from the stale cache and visibly blanks for a round-trip.
      await queryClient.invalidateQueries({ queryKey: ['study-availability'] })
      setPending(null)
    },
    onError: (err) =>
      setError(err instanceof ApiError ? err.message : 'Could not save your weekly template'),
  })

  if (isLoading) {
    return (
      <section aria-label="Weekly availability">
        <h2>Your weekly time blocks</h2>
        <p className="page-status">Loading your weekly template…</p>
      </section>
    )
  }

  // Saving replaces the stored template wholesale (delete-then-insert). If the
  // load failed, `slots` would fall back to an empty grid that looks like a
  // genuine "nothing set yet" — editing and saving from there would wipe the
  // real template. Refuse to offer the editor at all until we know the truth.
  if (loadError) {
    return (
      <section aria-label="Weekly availability">
        <h2>Your weekly time blocks</h2>
        <p role="alert" className="form-error">
          {loadError instanceof ApiError
            ? loadError.message
            : 'Could not load your weekly template'}{' '}
          — reload before editing, so you don’t overwrite what you already saved.
        </p>
      </section>
    )
  }

  return (
    <section aria-label="Weekly availability">
      <h2>Your weekly time blocks</h2>
      <p>
        Click a slot to cycle it: free → <span className="tag-study">study</span> →{' '}
        <span className="tag-blocked">blocked (classes, commitments)</span> → free.
      </p>
      <WeekGrid cellClass={(day, hour) => slots[slotKey(day, hour)] ?? ''} onCellClick={cycle} />
      {error && <p role="alert" className="form-error">{error}</p>}
      <button type="button" onClick={() => save.mutate()} disabled={save.isPending}>
        {save.isPending ? 'Saving…' : 'Save weekly template'}
      </button>
    </section>
  )
}

function targetKey(item: RemainingAssessment) {
  return `${item.enrolment_id}-${item.assessment_id ?? ''}-${item.custom_assessment_id ?? ''}`
}

function TargetsEditor() {
  const queryClient = useQueryClient()
  const { data: items, isLoading, error: loadError } = useQuery({
    queryKey: ['remaining-assessments'],
    queryFn: () => apiClient.get<RemainingAssessment[]>('/study-plans/remaining-assessments'),
  })
  const [edits, setEdits] = useState<Record<string, string>>({})
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)

  const editedTargets = (items ?? [])
    .filter((item) => edits[targetKey(item)]?.trim())

  const save = useMutation({
    mutationFn: () => {
      const targets = editedTargets
        .map((item) => ({
          enrolment_id: item.enrolment_id,
          assessment_id: item.assessment_id,
          custom_assessment_id: item.custom_assessment_id,
          target_percent: Number(edits[targetKey(item)]),
        }))
      return apiClient.put('/study-plans/targets', { targets })
    },
    onSuccess: () => {
      setSaved(true)
      setError(null)
      void queryClient.invalidateQueries({ queryKey: ['remaining-assessments'] })
    },
    onError: (err) =>
      setError(err instanceof ApiError ? err.message : 'Could not save your targets'),
  })

  // Loading and failure must not both collapse into "you have no assessments" —
  // that states something false about the student's record as if it were fact.
  if (isLoading) {
    return (
      <section aria-label="Assessment targets">
        <h2>Your target marks</h2>
        <p className="page-status">Loading your assessments…</p>
      </section>
    )
  }

  if (loadError) {
    return (
      <section aria-label="Assessment targets">
        <h2>Your target marks</h2>
        <p role="alert" className="form-error">
          {loadError instanceof ApiError
            ? loadError.message
            : 'Could not load your assessments — please try again.'}
        </p>
      </section>
    )
  }

  if (!items || items.length === 0) {
    return (
      <section aria-label="Assessment targets">
        <h2>Your target marks</h2>
        <p className="page-status">
          No remaining assessments — enrol in a course or add assessment items first.
        </p>
      </section>
    )
  }

  const byCourse = new Map<string, RemainingAssessment[]>()
  for (const item of items) {
    const list = byCourse.get(item.course_code) ?? []
    list.push(item)
    byCourse.set(item.course_code, list)
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    save.mutate()
  }

  return (
    <section aria-label="Assessment targets">
      <h2>Your target marks</h2>
      <p>Set a target mark for each remaining assessment — this drives how much study time it gets.</p>
      <form onSubmit={handleSubmit}>
        {[...byCourse.entries()].map(([courseCode, courseItems]) => (
          <div key={courseCode}>
            <h3>{courseCode}</h3>
            <ul className="session-list">
              {courseItems.map((item) => (
                <li key={targetKey(item)}>
                  <span>
                    {item.name} ({item.weight}%{item.due_date ? `, due ${item.due_date}` : ''})
                  </span>{' '}
                  <input
                    aria-label={`Target percent for ${item.name}`}
                    type="number"
                    min={0}
                    max={100}
                    placeholder={item.target_percent !== null ? String(item.target_percent) : '65'}
                    value={edits[targetKey(item)] ?? ''}
                    onChange={(e) => {
                      setEdits({ ...edits, [targetKey(item)]: e.target.value })
                      // Any new edit invalidates the previous confirmation —
                      // otherwise "Targets saved." sits there over unsaved work.
                      setSaved(false)
                    }}
                  />
                </li>
              ))}
            </ul>
          </div>
        ))}
        {error && <p role="alert" className="form-error">{error}</p>}
        {saved && !error && <p className="page-status">Targets saved.</p>}
        {/* Saving with no edits PUT an empty list, which the API accepts — so it
            reported "Targets saved." when nothing had been. */}
        <button type="submit" disabled={save.isPending || editedTargets.length === 0}>
          {save.isPending ? 'Saving…' : 'Save targets'}
        </button>
      </form>
    </section>
  )
}

function WeeklyBlocksView({ blocks }: { blocks: WeeklyStudyBlock[] }) {
  const byCell = new Map<string, WeeklyStudyBlock>()
  for (const block of blocks) {
    byCell.set(slotKey(block.day_of_week, block.start_hour), block)
  }
  return (
    <WeekGrid
      cellClass={(day, hour) => (byCell.has(slotKey(day, hour)) ? 'filled' : '')}
      cellContent={(day, hour) => {
        const block = byCell.get(slotKey(day, hour))
        return block ? <span title={block.focus}>{block.course_code}</span> : null
      }}
    />
  )
}

function GenerateSection() {
  const queryClient = useQueryClient()
  const [weekStart, setWeekStart] = useState(currentWeekMonday())
  const [plan, setPlan] = useState<WeeklyStudyPlan | null>(null)
  const [error, setError] = useState<string | null>(null)

  const generate = useMutation({
    mutationFn: () =>
      apiClient.post<WeeklyStudyPlan>('/study-plans/generate', { week_start: weekStart }),
    onSuccess: (data) => {
      setPlan(data)
      setError(null)
      void queryClient.invalidateQueries({ queryKey: ['weekly-study-plans'] })
    },
    onError: (err) =>
      setError(err instanceof ApiError ? err.message : 'Could not generate a plan'),
  })

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    generate.mutate()
  }

  return (
    <section aria-label="Generate weekly plan">
      <h2>Generate this week&rsquo;s plan</h2>
      <form onSubmit={handleSubmit} className="inline-form">
        <label>
          Week starting (Monday){' '}
          <input
            aria-label="Week start"
            type="date"
            value={weekStart}
            onChange={(e) => setWeekStart(e.target.value)}
          />
        </label>
        <button type="submit" disabled={generate.isPending}>
          {generate.isPending ? 'Generating…' : 'Generate'}
        </button>
      </form>
      {generate.isPending && (
        <p className="page-status" role="status">Building your weekly plan…</p>
      )}
      {error && <p role="alert" className="form-error">{error}</p>}
      {plan && (
        <div aria-live="polite">
          {plan.diagnostics.map((d) => (
            <p key={d.message} className="page-status">{d.message}</p>
          ))}
          <WeeklyBlocksView blocks={plan.blocks} />
          <p className="page-status">{plan.disclaimer}</p>
        </div>
      )}
    </section>
  )
}

function SavedPlansList() {
  const queryClient = useQueryClient()
  const { data: saved } = useQuery({
    queryKey: ['weekly-study-plans'],
    queryFn: () => apiClient.get<WeeklyStudyPlanSummary[]>('/study-plans'),
  })
  const [openId, setOpenId] = useState<number | null>(null)

  const openPlan = useQuery({
    queryKey: ['weekly-study-plan', openId],
    queryFn: () => apiClient.get<WeeklyStudyPlan>(`/study-plans/${openId}`),
    enabled: openId !== null,
  })

  const [removeError, setRemoveError] = useState<string | null>(null)
  const remove = useMutation({
    mutationFn: (id: number) => apiClient.delete(`/study-plans/${id}`),
    onSuccess: (_data, id) => {
      if (openId === id) setOpenId(null)
      setRemoveError(null)
      void queryClient.invalidateQueries({ queryKey: ['weekly-study-plans'] })
    },
    // Without this a failed delete just re-enables the button and leaves the
    // plan sitting there with no explanation.
    onError: (err) =>
      setRemoveError(err instanceof ApiError ? err.message : 'Could not delete that plan'),
  })

  if (!saved || saved.length === 0) return null

  return (
    <section aria-label="Saved weekly plans">
      <h2>Saved plans</h2>
      {removeError && <p role="alert" className="form-error">{removeError}</p>}
      <ul className="card-list">
        {saved.map((summary) => (
          <li key={summary.id} className="course-card">
            <div className="saved-plan-row">
              <strong>Week of {summary.week_start}</strong>
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
                      : 'Could not load that plan'}
                  </p>
                )}
                {openPlan.data && <WeeklyBlocksView blocks={openPlan.data.blocks} />}
              </div>
            )}
          </li>
        ))}
      </ul>
    </section>
  )
}

export function StudyPlanPage() {
  return (
    <main>
      <h1>Weekly study plan</h1>
      <p>
        Set your weekly time blocks and target marks once, then generate a study schedule that
        fits around your classes and commitments across all your in-progress courses.
      </p>
      <AvailabilityEditor />
      <TargetsEditor />
      <GenerateSection />
      <SavedPlansList />
    </main>
  )
}
