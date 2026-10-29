import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Plus, Send, Trash2 } from 'lucide-react'
import { Link, useSearchParams } from 'react-router-dom'
import { AiBadge, ErrorNote, PageHead, Sheet, Spinner } from '../../components/ui'
import { api } from '../../lib/api'
import { relative } from '../../lib/format'
import type { AiStatus, ChatMessage, Conversation, Home, Subject } from '../../lib/types'
import { useAction } from '../../lib/useAction'
import { useLoad } from '../../lib/useLoad'
import { CitationChip } from './LibraryPage'
import { Confidence } from './TopicPage'

const MODES = [
  { key: 'tutor', label: 'Teach me', hint: 'Explains in your style, then checks you understood' },
  { key: 'ask', label: 'Answer from my notes', hint: 'Only what your files say, with pages' },
  { key: 'explain_back', label: "I'll explain it", hint: 'You explain; it finds the gaps' },
] as const

interface Memory {
  profile: { pace: string; explain_style: string; background: string | null }
  memories: { id: number; kind: string; text: string; topic: string | null; created_at: string }[]
}

function CheckQuestion({ message, onGraded }: { message: ChatMessage; onGraded: (messages: ChatMessage[]) => void }) {
  const [answer, setAnswer] = useState('')
  const [confidence, setConfidence] = useState<number | null>(null)
  const [result, setResult] = useState<{ correct: boolean | null; feedback: string; expected: string; card_created: boolean } | null>(null)
  const { busy, error, run } = useAction()
  const submit = (e: FormEvent) => {
    e.preventDefault()
    run(async () => {
      const r = await api.post<{ correct: boolean | null; feedback: string; expected: string; card_created: boolean; messages: ChatMessage[] }>(`/api/tutor/messages/${message.id}/check`, { answer, confidence })
      setResult(r)
      onGraded(r.messages)
    })
  }
  return (
    <form className="check-box" onSubmit={submit}>
      <strong style={{ fontWeight: 600 }}>Check: </strong>{message.check?.question}
      {result ? (
        <p className="small" style={{ marginTop: 8 }}>
          <span className={`pill ${result.correct ? 'ok' : result.correct === false ? 'accent' : ''}`}>{result.correct ? 'Correct' : result.correct === false ? 'Not quite' : 'Recorded'}</span>{' '}
          {result.card_created && 'Saved as a revision card and remembered for next time.'}
        </p>
      ) : (
        <>
          <textarea className="textarea" rows={2} value={answer} onChange={(e) => setAnswer(e.target.value)} style={{ marginTop: 8 }} placeholder="Your answer, in your own words" required />
          <div className="row" style={{ gap: 8, marginTop: 8, flexWrap: 'wrap' }}>
            <span className="tiny muted">How sure?</span>
            <Confidence value={confidence} onChange={setConfidence} />
            <button className="btn small primary" type="submit" disabled={busy || !answer.trim()}>{busy ? 'Checking…' : 'Check'}</button>
          </div>
          <ErrorNote>{error}</ErrorNote>
        </>
      )}
    </form>
  )
}

function Chat({ conversation, onUpdated }: { conversation: Conversation; onUpdated: () => void }) {
  const { data, setData } = useLoad<Conversation>(`/api/tutor/conversations/${conversation.id}`)
  const [text, setText] = useState('')
  const [pending, setPending] = useState<string | null>(null)
  const { busy, error, run } = useAction()
  const end = useRef<HTMLDivElement>(null)
  useEffect(() => {
    end.current?.scrollIntoView({ block: 'end' })
  }, [data?.messages?.length, pending])

  const send = (e: FormEvent) => {
    e.preventDefault()
    const message = text.trim()
    if (!message) return
    setText('')
    setPending(message)
    run(async () => {
      try {
        await api.post(`/api/tutor/conversations/${conversation.id}/messages`, { text: message })
        setData(await api.get<Conversation>(`/api/tutor/conversations/${conversation.id}`))
        onUpdated()
      } finally {
        setPending(null)
      }
    })
  }
  const messages = data?.messages ?? []
  const mode = MODES.find((m) => m.key === conversation.mode)
  return (
    <div className="panel" style={{ padding: 16 }}>
      <div className="spread" style={{ marginBottom: 10 }}>
        <div>
          <strong style={{ fontWeight: 600 }}>{mode?.label}</strong>
          <span className="muted small"> · {conversation.topic ?? 'any topic'}</span>
        </div>
        {conversation.topic_id && <Link className="btn ghost small" to={`/topics/${conversation.topic_id}`}>Topic</Link>}
      </div>
      <div className="chat" aria-live="polite">
        {!data && <Spinner />}
        {data && messages.length === 0 && !pending && (
          <p className="muted small">
            {conversation.mode === 'explain_back' ? 'Explain the idea as if teaching a friend. The tutor will point out exactly what is missing.' : 'Ask anything. The tutor uses your own notes and cites the page.'}
          </p>
        )}
        {messages.map((m) => (
          <div key={m.id} className={`bubble ${m.role}`}>
            {m.content}
            {m.citations.length > 0 && <div className="cites">{m.citations.map((c, i) => <CitationChip key={i} c={c} />)}</div>}
            {m.check && <CheckQuestion message={m} onGraded={(extra) => setData((d) => d && { ...d, messages: [...(d.messages ?? []), ...extra.filter((x) => !(d.messages ?? []).some((y) => y.id === x.id))] })} />}
          </div>
        ))}
        {pending && <div className="bubble user">{pending}</div>}
        {pending && <div className="bubble tutor muted">Reading your notes…</div>}
        <div ref={end} />
      </div>
      <ErrorNote>{error}</ErrorNote>
      <form className="composer" onSubmit={send}>
        <textarea className="textarea" value={text} onChange={(e) => setText(e.target.value)} placeholder={conversation.mode === 'explain_back' ? 'Explain it in your own words…' : 'Ask a question…'}
          onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(e) } }} />
        <button className="btn primary" type="submit" disabled={busy || !text.trim()} aria-label="Send"><Send size={15} /></button>
      </form>
    </div>
  )
}

function MemoryView() {
  const { data, setData } = useLoad<Memory>('/api/tutor/memory')
  const { run } = useAction()
  if (!data) return <Spinner />
  return (
    <div className="stack">
      <p className="muted small">The tutor adapts to this. Change your pace, style and background in <Link to="/settings">Settings</Link>. Delete anything you don't want it to use.</p>
      <div className="panel small">
        <p><strong>Pace:</strong> {data.profile.pace} · <strong>Style:</strong> {data.profile.explain_style.replace('_', ' ')}</p>
        {data.profile.background && <p style={{ marginTop: 6 }}><strong>In your words:</strong> {data.profile.background}</p>}
      </div>
      {data.memories.length === 0 && <p className="muted">Nothing remembered yet.</p>}
      {data.memories.map((m) => (
        <div key={m.id} className="spread small" style={{ borderTop: '1px solid var(--rule)', paddingTop: 8 }}>
          <span><span className="pill">{m.kind}</span> {m.text} <span className="muted tiny">{m.topic && `· ${m.topic}`} · {relative(m.created_at)}</span></span>
          <button className="btn ghost icon small" type="button" aria-label="Forget this" onClick={() => run(async () => { await api.del(`/api/tutor/memory/${m.id}`); setData({ ...data, memories: data.memories.filter((x) => x.id !== m.id) }) })}><Trash2 size={13} /></button>
        </div>
      ))}
      {data.memories.length > 0 && <button className="btn ghost danger small" type="button" onClick={() => run(async () => { if (!window.confirm('Forget everything the tutor has learned about you?')) return; await api.del('/api/tutor/memory'); setData({ ...data, memories: [] }) })}>Forget everything</button>}
    </div>
  )
}

export function TutorPage() {
  const [params, setParams] = useSearchParams()
  const { data: threads, reload } = useLoad<Conversation[]>('/api/tutor/conversations')
  const { data: subjects } = useLoad<Subject[]>('/api/subjects')
  const { data: ai } = useLoad<AiStatus>('/api/ai/status')
  const { data: home } = useLoad<Home>('/api/home')
  const [mode, setMode] = useState<(typeof MODES)[number]['key']>('tutor')
  const [course, setCourse] = useState(params.get('course') ?? '')
  const [showMemory, setShowMemory] = useState(false)
  const { busy, error, run } = useAction()
  const autoStarted = useRef(false)
  const activeId = Number(params.get('conversation')) || null
  const active = threads?.find((t) => t.id === activeId) ?? null

  const create = (body: { mode: string; course_id?: number | null; topic_id?: number | null }) =>
    run(async () => {
      const c = await api.post<Conversation>('/api/tutor/conversations', body)
      await reload()
      setParams({ conversation: String(c.id) })
    })

  // Arriving from a topic ("Learn with the tutor") opens a tutoring session on it straight away.
  useEffect(() => {
    const topic = params.get('topic')
    if (topic && !activeId && !autoStarted.current) {
      autoStarted.current = true
      void create({ mode: 'tutor', topic_id: Number(topic) })
    }
  })

  return (
    <main className="page wide">
      <PageHead kicker="Personal tutor" title="Tutor">
        <AiBadge ai={ai} />
        <button className="btn" type="button" onClick={() => setShowMemory(true)}>What it knows about me</button>
      </PageHead>
      <ErrorNote>{error}</ErrorNote>
      <div className="tutor">
        <aside className="stack">
          <form className="panel stack" onSubmit={(e) => { e.preventDefault(); create({ mode, course_id: course ? Number(course) : null }) }}>
            <div className="stack tight">
              {MODES.map((m) => (
                <label key={m.key} className="check" style={{ display: 'flex', alignItems: 'flex-start', gap: 8 }}>
                  <input type="radio" name="mode" checked={mode === m.key} onChange={() => setMode(m.key)} />
                  <span><strong style={{ fontWeight: 500 }}>{m.label}</strong><span className="muted tiny" style={{ display: 'block' }}>{m.hint}</span></span>
                </label>
              ))}
            </div>
            <select className="select" value={course} onChange={(e) => setCourse(e.target.value)}>
              <option value="">All subjects</option>
              {subjects?.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
            <button className="btn primary" type="submit" disabled={busy}><Plus size={14} /> New session</button>
          </form>
          <div className="threads">
            {threads?.length === 0 && <p className="muted small" style={{ padding: 12 }}>No sessions yet.</p>}
            {threads?.map((t) => (
              <button key={t.id} type="button" aria-current={t.id === activeId} onClick={() => setParams({ conversation: String(t.id) })}>
                <span className="clip" style={{ display: 'block' }}>{t.title}</span>
                <small>{MODES.find((m) => m.key === t.mode)?.label}{t.topic && ` · ${t.topic}`} · {relative(t.updated_at)}</small>
              </button>
            ))}
          </div>
        </aside>
        <section>
          {active ? (
            <Chat key={active.id} conversation={active} onUpdated={reload} />
          ) : (
            <div className="panel" style={{ padding: 28 }}>
              <h2 className="title" style={{ fontSize: 28 }}>A tutor that knows how you learn.</h2>
              <p className="muted" style={{ marginTop: 10, maxWidth: '60ch' }}>
                It explains at your pace and in your preferred style, uses only your own notes (with the page for each point), checks your understanding with a question, and remembers what you got wrong so it can fix it next time.
                Wrong answers become revision cards automatically.
              </p>
              {ai && !ai.available && <p className="small" style={{ marginTop: 10, color: 'var(--warn)' }}>The AI model isn't configured on this server, so the tutor will show the relevant pages from your notes instead.</p>}
              {home && (home.study.weak_topics.length > 0 || home.exams.length > 0) && (
                <>
                  <p className="kicker" style={{ marginTop: 22 }}>Suggested for you, from your own results</p>
                  <div className="suggest-chips">
                    {home.study.weak_topics.slice(0, 3).map((w) => (
                      <button key={w.topic_id} type="button" className="suggest-chip" disabled={busy} onClick={() => create({ mode: 'tutor', topic_id: w.topic_id })}>
                        <strong style={{ fontWeight: 600 }}>Re-teach me {w.title}</strong>
                        <small>{w.reason}</small>
                      </button>
                    ))}
                    {home.exams.slice(0, 2).map((e) => (
                      <button key={e.id} type="button" className="suggest-chip" disabled={busy} onClick={() => create({ mode: 'tutor', course_id: e.course?.id ?? null })}>
                        <strong style={{ fontWeight: 600 }}>Prepare for {e.title}</strong>
                        <small>{e.hours_left < 48 ? `in ${Math.round(e.hours_left)}h` : `in ${Math.round(e.hours_left / 24)} days`} · {e.covered_count} of {e.topic_count} topics covered</small>
                      </button>
                    ))}
                    {home.study.weak_topics[0] && (
                      <button type="button" className="suggest-chip" disabled={busy} onClick={() => create({ mode: 'explain_back', topic_id: home.study.weak_topics[0].topic_id })}>
                        <strong style={{ fontWeight: 600 }}>Explain {home.study.weak_topics[0].title} back to me</strong>
                        <small>You teach it; the tutor points out the exact gaps</small>
                      </button>
                    )}
                  </div>
                </>
              )}
              <p className="small" style={{ marginTop: 14 }}>Or start a session on the left, or open a topic and choose “Learn with the tutor”.</p>
            </div>
          )}
        </section>
      </div>
      <Sheet open={showMemory} title="What the tutor knows about you" onClose={() => setShowMemory(false)}>
        <MemoryView />
      </Sheet>
    </main>
  )
}
