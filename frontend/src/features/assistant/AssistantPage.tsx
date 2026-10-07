import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import type { FormEvent, KeyboardEvent } from 'react'

import { ApiError, apiClient, streamPost } from '../../lib/apiClient'
import type { EnrolmentSummary } from '../../types/api'

interface ChatMessage {
  role: 'user' | 'assistant'
  text: string
}

export function AssistantPage() {
  const { data: enrolments } = useQuery({
    queryKey: ['enrolments'],
    queryFn: () => apiClient.get<EnrolmentSummary[]>('/enrolments'),
  })
  const [question, setQuestion] = useState('')
  const [enrolmentId, setEnrolmentId] = useState('')
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [isStreaming, setIsStreaming] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const current = (enrolments ?? []).filter((e) => e.status === 'in_progress')
  const lastMessage = messages[messages.length - 1]
  const lastAnswer = lastMessage?.role === 'assistant' ? lastMessage.text : ''

  function appendToAssistant(chunk: string) {
    setMessages((prev) => {
      const next = [...prev]
      const last = next[next.length - 1]
      next[next.length - 1] = { role: 'assistant', text: last.text + chunk }
      return next
    })
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    // Enter also confirms a candidate in an input method (pinyin, kana, ...).
    // keyCode 229 covers Safari, which reports the confirming keydown as
    // composing-ended; sending then would submit a half-typed question.
    if (event.nativeEvent.isComposing || event.keyCode === 229) return
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      event.currentTarget.form?.requestSubmit()
    }
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    const trimmed = question.trim()
    if (!trimmed || isStreaming) return

    setError(null)
    setQuestion('')
    setMessages((prev) => [
      ...prev,
      { role: 'user', text: trimmed },
      { role: 'assistant', text: '' },
    ])
    setIsStreaming(true)

    try {
      await streamPost(
        '/assistant/ask/stream',
        { question: trimmed, enrolment_id: enrolmentId ? Number(enrolmentId) : null },
        appendToAssistant,
      )
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : 'The assistant could not answer just now.',
      )
      // Drop the empty assistant bubble if nothing streamed in.
      setMessages((prev) => {
        const last = prev[prev.length - 1]
        return last && last.role === 'assistant' && last.text === '' ? prev.slice(0, -1) : prev
      })
    } finally {
      setIsStreaming(false)
    }
  }

  return (
    <main>
      <h1>Study assistant</h1>
      <p>
        Ask about your progress. Answers are grounded in Gradient's deterministic figures
        (GPA, secured marks, projected grade) and stream in as they are written.
      </p>

      {messages.length > 0 && (
        <section className="chat-log" aria-label="Conversation">
          {messages.map((message, index) => {
            const isStreamingReply =
              isStreaming && message.role === 'assistant' && index === messages.length - 1
            return (
              <div key={index} className={`chat-message chat-${message.role}`}>
                <span className="chat-role">
                  {message.role === 'user' ? 'You' : 'Assistant'}
                </span>
                <p>{message.text}</p>
                {isStreamingReply && (
                  <span className="typing-indicator" aria-hidden="true">
                    <span />
                    <span />
                    <span />
                  </span>
                )}
              </div>
            )
          })}
        </section>
      )}
      {/* Announce that the assistant is working, then the finished answer once
          (not on every streamed chunk). */}
      <p className="sr-only" role="status">
        {isStreaming ? 'Assistant is responding…' : lastAnswer}
      </p>

      {error && (
        <p role="alert" className="form-error">
          {error}
        </p>
      )}

      <form onSubmit={handleSubmit} className="inline-form">
        {current.length > 0 && (
          <select
            aria-label="Course context (optional)"
            value={enrolmentId}
            onChange={(e) => setEnrolmentId(e.target.value)}
          >
            <option value="">General (no course)</option>
            {current.map((enrolment) => (
              <option key={enrolment.enrolment_id} value={enrolment.enrolment_id}>
                {enrolment.course_code}
              </option>
            ))}
          </select>
        )}
        <textarea
          aria-label="Your question"
          className="assistant-question"
          placeholder="e.g. What do I need on my final? (Shift+Enter for a new line)"
          rows={3}
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={handleKeyDown}
        />
        <button type="submit" disabled={isStreaming || !question.trim()}>
          {isStreaming ? 'Answering…' : 'Ask'}
        </button>
      </form>
    </main>
  )
}
