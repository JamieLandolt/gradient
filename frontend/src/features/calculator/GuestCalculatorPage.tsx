import { useState } from 'react'
import type { FormEvent } from 'react'

import { ApiError, apiClient } from '../../lib/apiClient'

interface CalculatorItem {
  name: string
  weight: string
  score: string
}

interface WhatIfResult {
  status: 'reachable' | 'already_secured' | 'not_reachable' | 'locked'
  target_grade: number
  target_percent: number
  required_average_percent: number | null
  hurdle_warnings: string[]
  final_grade: number | null
  standing: { secured_percent: number; remaining_weight: number }
}

const STATUS_LABELS: Record<WhatIfResult['status'], string> = {
  reachable: 'Reachable',
  already_secured: 'Already secured',
  not_reachable: 'Not reachable',
  locked: 'All assessment complete — grade locked',
}

const EMPTY_ITEM: CalculatorItem = { name: '', weight: '', score: '' }

export function GuestCalculatorPage() {
  const [items, setItems] = useState<CalculatorItem[]>([
    { name: 'Assignment 1', weight: '40', score: '' },
    { name: 'Final Exam', weight: '60', score: '' },
  ])
  const [targetGrade, setTargetGrade] = useState(4)
  const [result, setResult] = useState<WhatIfResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  function updateItem(index: number, field: keyof CalculatorItem, value: string) {
    setItems((current) =>
      current.map((item, i) => (i === index ? { ...item, [field]: value } : item)),
    )
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setError(null)
    try {
      const payload = {
        items: items
          .filter((item) => item.name.trim() && item.weight !== '')
          .map((item) => ({
            name: item.name.trim(),
            weight: Number(item.weight),
            score: item.score === '' ? null : Number(item.score),
          })),
        target_grade: targetGrade,
      }
      const data = await apiClient.post<WhatIfResult>('/calculator/what-if', payload)
      setResult(data)
    } catch (err) {
      setResult(null)
      setError(err instanceof ApiError ? err.message : 'Something went wrong.')
    }
  }

  return (
    <main>
      <h1>Target-grade calculator</h1>
      <p>
        Enter your assessment items (weights must sum to 100) and any marks you already have —
        no account needed, nothing is saved.
      </p>
      <form onSubmit={handleSubmit}>
        <table className="calculator-table">
          <thead>
            <tr>
              <th scope="col">Assessment</th>
              <th scope="col">Weight %</th>
              <th scope="col">Score /100 (blank if not done)</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item, index) => (
              <tr key={index}>
                <td>
                  <input
                    aria-label={`Item ${index + 1} name`}
                    value={item.name}
                    onChange={(e) => updateItem(index, 'name', e.target.value)}
                  />
                </td>
                <td>
                  <input
                    aria-label={`Item ${index + 1} weight`}
                    type="number"
                    min="0"
                    max="100"
                    value={item.weight}
                    onChange={(e) => updateItem(index, 'weight', e.target.value)}
                  />
                </td>
                <td>
                  <input
                    aria-label={`Item ${index + 1} score`}
                    type="number"
                    min="0"
                    max="100"
                    value={item.score}
                    onChange={(e) => updateItem(index, 'score', e.target.value)}
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="calculator-actions">
          <button type="button" onClick={() => setItems((c) => [...c, { ...EMPTY_ITEM }])}>
            Add item
          </button>
          <label>
            Target grade{' '}
            <select
              value={targetGrade}
              onChange={(e) => setTargetGrade(Number(e.target.value))}
            >
              {[4, 5, 6, 7].map((grade) => (
                <option key={grade} value={grade}>
                  {grade}
                </option>
              ))}
            </select>
          </label>
          <button type="submit">Calculate</button>
        </div>
      </form>

      {error && <p role="alert" className="form-error">{error}</p>}
      {result && (
        <section aria-live="polite" className={`result-card status-${result.status}`}>
          <h2>{STATUS_LABELS[result.status]}</h2>
          <p>
            Secured so far: <strong>{result.standing.secured_percent.toFixed(1)}%</strong>{' '}
            with {result.standing.remaining_weight.toFixed(0)}% still to come.
          </p>
          {result.status === 'reachable' && result.required_average_percent !== null && (
            <p>
              You need an average of{' '}
              <strong>{result.required_average_percent.toFixed(1)}%</strong> across the
              remaining assessment to reach a grade {result.target_grade} (
              {result.target_percent}%).
            </p>
          )}
          {result.status === 'locked' && result.final_grade !== null && (
            <p>Final grade: <strong>{result.final_grade}</strong></p>
          )}
          {result.hurdle_warnings.map((warning) => (
            <p key={warning} className="hurdle-warning" role="alert">
              ⚠ {warning}
            </p>
          ))}
        </section>
      )}
    </main>
  )
}
