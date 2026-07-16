import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { expect, test, vi } from 'vitest'

import type { Course } from '../types/api'
import { CourseSearchSelect } from './CourseSearchSelect'

const COURSES: Course[] = [
  { id: 1, code: 'CSSE1001', title: 'Introduction to Software Engineering', units: 2, description: '' },
  { id: 2, code: 'COMP3506', title: 'Algorithms & Data Structures', units: 2, description: '' },
  { id: 3, code: 'COMP3702', title: 'Artificial Intelligence', units: 2, description: '' },
  { id: 4, code: 'MATH1051', title: 'Calculus & Linear Algebra I', units: 2, description: '' },
  { id: 5, code: 'STAT1201', title: 'Analysis of Scientific Data', units: 2, description: '' },
]

function Harness({ onChange = vi.fn() }: { onChange?: (code: string) => void }) {
  const [value, setValue] = useState('')
  return (
    <CourseSearchSelect
      courses={COURSES}
      value={value}
      onChange={(code) => {
        setValue(code)
        onChange(code)
      }}
    />
  )
}

const combobox = () => screen.getByRole('combobox', { name: 'Course' })

test('typing narrows the list to matching courses', async () => {
  const user = userEvent.setup()
  render(<Harness />)

  await user.type(combobox(), 'algor')

  expect(screen.getByRole('option', { name: /COMP3506/ })).toBeInTheDocument()
  expect(screen.queryByRole('option', { name: /MATH1051/ })).not.toBeInTheDocument()
})

test('matches on course code as well as title', async () => {
  const user = userEvent.setup()
  render(<Harness />)

  await user.type(combobox(), 'math')

  expect(screen.getByRole('option', { name: /MATH1051/ })).toBeInTheDocument()
  expect(screen.queryByRole('option', { name: /COMP3506/ })).not.toBeInTheDocument()
})

test('a code prefix ranks its own course first', async () => {
  const user = userEvent.setup()
  render(<Harness />)

  await user.type(combobox(), 'comp37')
  const options = screen.getAllByRole('option')

  expect(options[0]).toHaveTextContent('COMP3702')
})

test('clicking a result selects it and closes the list', async () => {
  const user = userEvent.setup()
  const onChange = vi.fn()
  render(<Harness onChange={onChange} />)

  await user.type(combobox(), 'algor')
  await user.click(screen.getByRole('option', { name: /COMP3506/ }))

  expect(onChange).toHaveBeenCalledWith('COMP3506')
  expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
  // The selection stays visible once the query is cleared.
  expect(combobox()).toHaveAttribute('placeholder', expect.stringContaining('COMP3506'))
})

test('arrow keys move the highlight and Enter picks it', async () => {
  const user = userEvent.setup()
  const onChange = vi.fn()
  render(<Harness onChange={onChange} />)

  await user.type(combobox(), 'comp')
  await user.keyboard('{ArrowDown}{Enter}')

  // 'comp' matches COMP3506 and COMP3702 (sorted by code); ArrowDown -> the 2nd.
  expect(onChange).toHaveBeenCalledWith('COMP3702')
})

test('Enter on a highlighted option does not submit the surrounding form', async () => {
  const user = userEvent.setup()
  const onSubmit = vi.fn((e) => e.preventDefault())
  render(
    <form onSubmit={onSubmit}>
      <Harness />
    </form>,
  )

  await user.type(combobox(), 'algor')
  await user.keyboard('{Enter}')

  expect(onSubmit).not.toHaveBeenCalled()
})

test('an unmatched query says so instead of showing an empty box', async () => {
  const user = userEvent.setup()
  render(<Harness />)

  await user.type(combobox(), 'zzzz')

  expect(screen.getByText(/No courses match/)).toBeInTheDocument()
  expect(screen.queryAllByRole('option')).toHaveLength(0)
})

test('the selection can be cleared', async () => {
  const user = userEvent.setup()
  const onChange = vi.fn()
  render(<Harness onChange={onChange} />)

  await user.type(combobox(), 'algor')
  await user.click(screen.getByRole('option', { name: /COMP3506/ }))
  await user.click(screen.getByRole('button', { name: /Clear selected course/ }))

  expect(onChange).toHaveBeenLastCalledWith('')
})

test('Escape closes the list without selecting', async () => {
  const user = userEvent.setup()
  const onChange = vi.fn()
  render(<Harness onChange={onChange} />)

  await user.type(combobox(), 'algor')
  await user.keyboard('{Escape}')

  expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
  expect(onChange).not.toHaveBeenCalled()
})

test('the listbox is wired to the combobox for screen readers', async () => {
  const user = userEvent.setup()
  render(<Harness />)

  await user.type(combobox(), 'comp')

  const input = combobox()
  expect(input).toHaveAttribute('aria-expanded', 'true')
  expect(input).toHaveAttribute('aria-controls', screen.getByRole('listbox').id)
  // The highlighted option is announced while focus stays in the input.
  expect(input.getAttribute('aria-activedescendant')).toBe(
    screen.getAllByRole('option')[0].id,
  )
})
