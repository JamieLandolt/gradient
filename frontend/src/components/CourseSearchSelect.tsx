import { useEffect, useMemo, useRef, useState } from 'react'

import type { Course } from '../types/api'

/** Cap the rendered list. The catalogue is small today but grows with every
 *  import, and an unbounded dropdown is exactly what this replaces. */
const MAX_VISIBLE = 8

function matches(course: Course, query: string): boolean {
  const needle = query.trim().toLowerCase()
  if (!needle) return true
  // Match on code and title only — descriptions are long enough that matching
  // them makes the results look arbitrary ("why is CIVL2210 in here?").
  return (
    course.code.toLowerCase().includes(needle) ||
    course.title.toLowerCase().includes(needle)
  )
}

/** Rank exact/prefix code matches first: someone typing "COMP35" wants COMP3506
 *  at the top, not the first course that happens to mention it. */
function rank(course: Course, query: string): number {
  const needle = query.trim().toLowerCase()
  if (!needle) return 2
  const code = course.code.toLowerCase()
  if (code === needle) return 0
  if (code.startsWith(needle)) return 1
  if (course.title.toLowerCase().startsWith(needle)) return 2
  return 3
}

export function CourseSearchSelect({
  courses,
  value,
  onChange,
  label = 'Course',
  id = 'course-search',
}: {
  courses: Course[]
  /** The selected course code, or '' for none. */
  value: string
  onChange: (code: string) => void
  label?: string
  id?: string
}) {
  const [query, setQuery] = useState('')
  const [isOpen, setIsOpen] = useState(false)
  const [activeIndex, setActiveIndex] = useState(0)
  const rootRef = useRef<HTMLDivElement>(null)

  const selected = courses.find((course) => course.code === value) ?? null

  const results = useMemo(() => {
    const filtered = courses.filter((course) => matches(course, query))
    return [...filtered]
      .sort((a, b) => rank(a, query) - rank(b, query) || a.code.localeCompare(b.code))
      .slice(0, MAX_VISIBLE)
  }, [courses, query])

  // Keep the highlight in range as the list shrinks under typing.
  useEffect(() => setActiveIndex(0), [query])

  // Close on an outside click, so the list doesn't hang over the rest of the form.
  useEffect(() => {
    if (!isOpen) return
    function onPointerDown(event: MouseEvent) {
      if (!rootRef.current?.contains(event.target as Node)) setIsOpen(false)
    }
    document.addEventListener('mousedown', onPointerDown)
    return () => document.removeEventListener('mousedown', onPointerDown)
  }, [isOpen])

  function select(course: Course) {
    onChange(course.code)
    setQuery('')
    setIsOpen(false)
  }

  function handleKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault()
      if (!isOpen) {
        setIsOpen(true)
        return
      }
      const step = event.key === 'ArrowDown' ? 1 : -1
      setActiveIndex((current) => {
        if (results.length === 0) return 0
        return (current + step + results.length) % results.length
      })
      return
    }
    if (event.key === 'Enter' && isOpen && results[activeIndex]) {
      event.preventDefault() // don't submit the form on the keystroke that picks
      select(results[activeIndex])
      return
    }
    if (event.key === 'Escape') {
      setIsOpen(false)
    }
  }

  const listboxId = `${id}-listbox`

  return (
    <div className="course-search" ref={rootRef}>
      <input
        id={id}
        className="course-search-input"
        // role=combobox + aria-activedescendant is the pattern that lets a
        // screen reader announce the highlighted option while focus stays here.
        role="combobox"
        aria-label={label}
        aria-expanded={isOpen}
        aria-controls={listboxId}
        aria-autocomplete="list"
        aria-activedescendant={
          isOpen && results[activeIndex] ? `${id}-opt-${results[activeIndex].code}` : undefined
        }
        autoComplete="off"
        placeholder={selected ? `${selected.code} — ${selected.title}` : 'Search courses…'}
        value={query}
        onChange={(e) => {
          setQuery(e.target.value)
          setIsOpen(true)
        }}
        onFocus={() => setIsOpen(true)}
        onKeyDown={handleKeyDown}
      />
      {selected && !query && (
        <button
          type="button"
          className="course-search-clear"
          aria-label={`Clear selected course ${selected.code}`}
          onClick={() => {
            onChange('')
            setQuery('')
          }}
        >
          ×
        </button>
      )}
      {isOpen && (
        <ul className="course-search-results" id={listboxId} role="listbox" aria-label={label}>
          {results.length === 0 && (
            <li className="course-search-empty" role="presentation">
              No courses match “{query.trim()}”
            </li>
          )}
          {results.map((course, index) => (
            <li
              key={course.code}
              id={`${id}-opt-${course.code}`}
              role="option"
              aria-selected={course.code === value}
              className={`course-search-option${index === activeIndex ? ' is-active' : ''}`}
              // mousedown, not click: the input's blur would otherwise close the
              // list before the click landed.
              onMouseDown={(e) => {
                e.preventDefault()
                select(course)
              }}
              onMouseEnter={() => setActiveIndex(index)}
            >
              <span className="course-search-code">{course.code}</span>
              <span className="course-search-title">{course.title}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
