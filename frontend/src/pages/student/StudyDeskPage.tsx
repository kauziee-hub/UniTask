import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Check, Flag, Pause, Play, Plus, X } from 'lucide-react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ErrorNote, Sheet, Spinner } from '../../components/ui'
import { api, type WorkItem } from '../../lib/api'
import { dueLabel, minutesLabel, relative } from '../../lib/format'
import type { Card, Citation, Session, TopicStatus } from '../../lib/types'
import { useAction } from '../../lib/useAction'
import { useLoad } from '../../lib/useLoad'
import { CitationChip } from './LibraryPage'

interface DeskData extends Session {
  work: WorkItem | null
  topic: { id: number; title: string; status: TopicStatus; course: { id: number; name: string } | null; weak_reason: string | null } | null
  exam: { id: number; title: string; starts_at: string } | null
  course_id: number | null
  materials: Citation[]
  due_cards: Card[]
  previous_minutes: number
}

/** The current time, refreshed every second while the timer runs. */
function useNow(active: boolean) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (!active) return
    const timer = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [active])
  return now
}

function clockText(seconds: number) {
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = seconds % 60
  const pad = (n: number) => String(n).padStart(2, '0')
  return h ? `${h}:${pad(m)}:${pad(s)}` : `${pad(m)}:${pad(s)}`
}

function PageReader({ citation, onClose }: { citation: Citation; onClose: () => void }) {
  const [page, setPage] = useState(citation.page)
  const { data } = useLoad<{ text: string; page: number; page_count: number | null }>(`/api/materials/${citation.material_id}/pages/${page}`)
  return (
    <div className="panel">
      <div className="spread">
        <strong style={{ fontWeight: 500 }} className="clip">{citation.title} · page {page}</strong>
        <span className="row" style={{ gap: 4 }}>
          <button className="btn ghost small" type="button" disabled={page <= 1} onClick={() => setPage(page - 1)}>‹</button>
          <button className="btn ghost small" type="button" disabled={Boolean(data?.page_count && page >= data.page_count)} onClick={() => setPage(page + 1)}>›</button>
          <Link className="btn ghost small" to={`/library/${citation.material_id}?page=${page}`} target="_blank">Open</Link>
          <button className="btn ghost icon small" type="button" aria-label="Close reader" onClick={onClose}><X size={13} /></button>
        </span>
      </div>
      <div className="page-text" style={{ marginTop: 10, maxHeight: 380, padding: 16 }}>{data ? data.text || 'No text on this page.' : 'Loading…'}</div>
    </div>
  )
}

function QuickCards({ cards }: { cards: Card[] }) {
  const [index, setIndex] = useState(0)
  const [shown, setShown] = useState(false)
  const { busy, run } = useAction()
  const card = cards[index]
  if (!card) return <p className="muted small">{cards.length ? 'All due cards reviewed.' : 'No flashcards due for this.'}</p>
  const grade = (g: string) => run(async () => { await api.post(`/api/cards/${card.id}/review`, { grade: g }); setShown(false); setIndex(index + 1) })
  return (
    <div>
      <p className="muted tiny">{index + 1} of {cards.length}</p>
      <p style={{ fontWeight: 500, marginTop: 4 }}>{card.front}</p>
      {shown ? (
        <>
          <p className="small" style={{ marginTop: 8 }}>{card.back}</p>
          <div className="row" style={{ gap: 6, marginTop: 10 }}>
            {['again', 'hard', 'good', 'easy'].map((g) => <button key={g} className="btn small" type="button" disabled={busy} onClick={() => grade(g)}>{g}</button>)}
          </div>
        </>
      ) : <button className="btn small" type="button" style={{ marginTop: 8 }} onClick={() => setShown(true)}>Show answer</button>}
    </div>
  )
}

function AskInline({ desk }: { desk: DeskData }) {
  const [q, setQ] = useState('')
  const [answer, setAnswer] = useState<{ answer: string; citations: Citation[] } | null>(null)
  const { busy, error, run } = useAction()
  const submit = (e: FormEvent) => {
    e.preventDefault()
    run(async () => setAnswer(await api.post('/api/ask', { question: q, course_id: desk.course_id, topic_id: desk.topic?.id ?? null })))
  }
  return (
    <form className="stack" onSubmit={submit}>
      <div className="row" style={{ gap: 6 }}>
        <input className="input" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Stuck? Ask about your own notes" style={{ flex: 1 }} />
        <button className="btn" type="submit" disabled={busy || q.trim().length < 2}>{busy ? '…' : 'Ask'}</button>
      </div>
      <ErrorNote>{error}</ErrorNote>
      {answer && (
        <div className="small" style={{ whiteSpace: 'pre-wrap', lineHeight: 1.6 }}>
          {answer.answer}
          <div className="row" style={{ gap: 6, flexWrap: 'wrap', marginTop: 8 }}>{answer.citations.map((c, i) => <CitationChip key={i} c={c} />)}</div>
        </div>
      )}
      {desk.topic && <Link className="small" to={`/tutor?topic=${desk.topic.id}`}>Open a full tutor session on {desk.topic.title} →</Link>}
    </form>
  )
}

export function StudyDeskPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const { data, setData, error } = useLoad<DeskData>(`/api/sessions/${id}`)
  const [scratch, setScratch] = useState<string | null>(null)
  const [saved, setSaved] = useState<'saved' | 'saving' | 'unsaved'>('saved')
  const [reading, setReading] = useState<Citation | null>(null)
  const [ending, setEnding] = useState(false)
  const [newItem, setNewItem] = useState('')
  const action = useAction()
  const saveTimer = useRef<number | undefined>(undefined)

  const now = useNow(data?.state === 'active')

  // Notes save themselves a moment after typing stops, so a refresh never loses them.
  useEffect(() => {
    if (scratch === null || !data || scratch === (data.scratch ?? '')) return
    window.clearTimeout(saveTimer.current)
    saveTimer.current = window.setTimeout(async () => {
      setSaved('saving')
      try {
        const updated = await api.patch<Session>(`/api/sessions/${data.id}`, { scratch })
        setData((d) => d && { ...d, scratch: updated.scratch })
        setSaved('saved')
      } catch {
        setSaved('unsaved')
      }
    }, 900)
    return () => window.clearTimeout(saveTimer.current)
  }, [scratch, data, setData])

  if (!data) return <main className="page">{error ? <ErrorNote>{error}</ErrorNote> : <Spinner label="Opening your desk" />}</main>

  const runningSince = Date.parse(data.resumed_at ?? data.started_at)
  const elapsed = data.state === 'active' ? data.accumulated_seconds + Math.floor((now - runningSince) / 1000) : data.elapsed_seconds
  const planned = data.planned_minutes * 60
  const ended = data.state === 'completed' || data.state === 'abandoned'

  const transition = (to: 'pause' | 'resume' | 'abandon') =>
    action.run(async () => {
      const s = await api.post<Session>(`/api/sessions/${data.id}/${to}`)
      setData({ ...data, ...s })
      if (to === 'abandon') navigate('/')
    })
  const checklist = (items: Session['checklist']) =>
    action.run(async () => {
      const s = await api.patch<Session>(`/api/sessions/${data.id}`, { checklist: items })
      setData({ ...data, checklist: s.checklist })
    })
  const complete = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const f = new FormData(event.currentTarget)
    action.run(async () => {
      if (scratch !== null && scratch !== (data.scratch ?? '')) await api.patch(`/api/sessions/${data.id}`, { scratch })
      const s = await api.post<Session>(`/api/sessions/${data.id}/complete`, { outcome: f.get('outcome') || null, topic_status: f.get('topic_status') || null })
      setData({ ...data, ...s })
      setEnding(false)
    })
  }

  return (
    <main className="page wide">
      <div className="desk-bar">
        <div style={{ minWidth: 0, flex: 1 }}>
          <p className="kicker">{{ assignment: 'Assignment', topic: 'Topic', revision: 'Revision', rescue: 'Exam rescue' }[data.kind] ?? 'Focus'} · Study desk</p>
          <h1 className="title clip" style={{ fontSize: 26, marginTop: 2 }}>{data.title}</h1>
        </div>
        <div style={{ textAlign: 'right' }}>
          <div className={`timer${elapsed > planned && !ended ? ' over' : ''}`} aria-live="off">{clockText(Math.max(0, elapsed))}</div>
          <span className="muted tiny">of {minutesLabel(data.planned_minutes)} planned{data.previous_minutes ? ` · ${minutesLabel(data.previous_minutes)} in earlier sessions` : ''}</span>
        </div>
        {!ended && (
          <div className="row" style={{ gap: 6 }}>
            {data.state === 'active' ? (
              <button className="btn" type="button" onClick={() => transition('pause')} disabled={action.busy}><Pause size={14} /> Pause</button>
            ) : (
              <button className="btn primary" type="button" onClick={() => transition('resume')} disabled={action.busy}><Play size={14} /> Resume</button>
            )}
            <button className="btn primary" type="button" onClick={() => setEnding(true)}><Flag size={14} /> Finish</button>
          </div>
        )}
      </div>
      <ErrorNote>{action.error}</ErrorNote>
      {ended && (
        <div className="note ok" style={{ marginBottom: 16, flexWrap: 'wrap', alignItems: 'center' }}>
          <span style={{ flex: 1 }}>Session {data.state}: {minutesLabel(Math.round(data.elapsed_seconds / 60))} focused{data.outcome && ` · “${data.outcome}”`}.</span>
          <Link className="btn small" to="/">Back to Today</Link>
        </div>
      )}

      <div className="desk">
        <div className="stack" style={{ gap: 18 }}>
          {data.work && (
            <section className="panel">
              <div className="spread"><h3>The assignment</h3><Link className="btn ghost small" to={`/work/${data.work.id}`}>Workspace</Link></div>
              <p className="small muted" style={{ marginTop: 4 }}>{data.work.due_at ? `Due ${dueLabel(data.work.due_at)} (${relative(data.work.due_at)})` : 'No due date'}{data.work.course && ` · ${data.work.course.name}`}</p>
              {data.work.instructions && <p className="prose small" style={{ marginTop: 8, maxHeight: 180, overflowY: 'auto' }}>{data.work.instructions}</p>}
            </section>
          )}
          {data.topic && (
            <section className="panel">
              <div className="spread"><h3>{data.topic.title}</h3><Link className="btn ghost small" to={`/topics/${data.topic.id}`}>Topic</Link></div>
              <p className="small muted" style={{ marginTop: 4 }}>{data.topic.course?.name} · coverage: {data.topic.status.replace('_', ' ')}</p>
              {data.topic.weak_reason && <p className="small" style={{ color: 'var(--accent)', marginTop: 4 }}>Weak spot: {data.topic.weak_reason}</p>}
              {data.exam && <p className="small" style={{ marginTop: 4 }}>For <Link to={`/exams/${data.exam.id}`}>{data.exam.title}</Link>, {relative(data.exam.starts_at)}</p>}
            </section>
          )}
          {reading ? <PageReader citation={reading} onClose={() => setReading(null)} /> : null}
          <section className="panel">
            <h3>From your materials</h3>
            {data.materials.length === 0 ? (
              <p className="muted small" style={{ marginTop: 4 }}>Nothing in your library matches this yet. <Link to="/library">Upload notes</Link>.</p>
            ) : (
              <div style={{ marginTop: 6 }}>
                {data.materials.map((m, i) => (
                  <div key={i} className="hit">
                    <button className="btn ghost small" type="button" style={{ padding: 0, height: 'auto', fontWeight: 500 }} onClick={() => setReading(m)}>{m.title} · page {m.page}</button>
                    <p className="muted small" style={{ marginTop: 2 }}>{m.excerpt}</p>
                  </div>
                ))}
              </div>
            )}
          </section>
          <section className="panel">
            <h3>Due flashcards</h3>
            <div style={{ marginTop: 8 }}><QuickCards cards={data.due_cards} /></div>
          </section>
        </div>

        <div className="stack" style={{ gap: 18 }}>
          <section className="panel">
            <h3>Checklist</h3>
            <ul className="checklist" style={{ marginTop: 6 }}>
              {data.checklist.map((item, i) => (
                <li key={i} className={item.done ? 'done' : undefined}>
                  <input type="checkbox" checked={item.done} onChange={() => checklist(data.checklist.map((c, j) => (j === i ? { ...c, done: !c.done } : c)))} aria-label={item.text} />
                  <span>{item.text}</span>
                  <button className="btn ghost icon small" type="button" aria-label="Remove" onClick={() => checklist(data.checklist.filter((_, j) => j !== i))}><X size={12} /></button>
                </li>
              ))}
            </ul>
            <form className="row" style={{ gap: 6, marginTop: 6 }} onSubmit={(e) => { e.preventDefault(); if (newItem.trim()) { checklist([...data.checklist, { text: newItem.trim(), done: false }]); setNewItem('') } }}>
              <input className="input" value={newItem} onChange={(e) => setNewItem(e.target.value)} placeholder="Add a step for this session" style={{ flex: 1, height: 32 }} />
              <button className="btn small" type="submit"><Plus size={13} /></button>
            </form>
          </section>
          <section className="panel">
            <div className="spread"><h3>Notes and draft</h3><span className="muted tiny">{saved === 'saved' ? 'Saved' : saved === 'saving' ? 'Saving…' : 'Not saved yet'}</span></div>
            <textarea className="textarea scratch" style={{ marginTop: 8 }} value={scratch ?? data.scratch ?? ''} onChange={(e) => { setScratch(e.target.value); setSaved('unsaved') }} placeholder="Work here. Everything is saved to your account as you type." />
          </section>
          <section className="panel">
            <h3>Ask while you work</h3>
            <div style={{ marginTop: 8 }}><AskInline desk={data} /></div>
          </section>
          {!ended && <button className="btn ghost danger small" type="button" onClick={() => { if (window.confirm('Abandon this session? Time so far is still recorded.')) transition('abandon') }}>Abandon session</button>}
        </div>
      </div>

      <Sheet open={ending} title="Finish the session" onClose={() => setEnding(false)}>
        <form className="stack" onSubmit={complete}>
          <label className="field"><span>What did you get done?</span><textarea className="textarea" name="outcome" rows={3} placeholder="Finished the FIRST/FOLLOW table; LL(1) conflicts still unclear." /></label>
          {data.topic && (
            <label className="field">
              <span>Where are you with {data.topic.title}?</span>
              <select className="select" name="topic_status" defaultValue="in_progress">
                <option value="in_progress">Started, not finished</option>
                <option value="revised">Revised it</option>
                <option value="practised">Practised questions on it</option>
              </select>
            </label>
          )}
          <button className="btn primary" type="submit" disabled={action.busy}><Check size={14} /> Save and finish</button>
        </form>
      </Sheet>
    </main>
  )
}
