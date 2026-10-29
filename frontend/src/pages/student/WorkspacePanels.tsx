import { useEffect, useRef, useState, type FormEvent } from 'react'
import { AlarmClockOff, Check, Play, Plus, Sparkles, X } from 'lucide-react'
import { Link, useNavigate } from 'react-router-dom'
import { ErrorNote, Meter } from '../../components/ui'
import { api, type WorkItem } from '../../lib/api'
import { dueLabel, fromLocalInput, minutesLabel, relative, toLocalInput } from '../../lib/format'
import type { Citation, Session } from '../../lib/types'
import { useAction } from '../../lib/useAction'
import { CitationChip } from './LibraryPage'
import { startSession } from '../../lib/study'

interface Subtask { id: number; title: string; done: boolean; minutes: number | null; origin: string }
export interface Workspace {
  item: WorkItem
  subtasks: Subtask[]
  materials: Citation[]
  topics: { id: number; title: string; status: string }[]
  sessions: Session[]
  spent_minutes: number
  remaining_minutes: number
  sources: { provider: string; url: string | null; last_seen_at: string }[]
  checklist_done: number
}

export function WorkspaceMain({ space }: { space: Workspace }) {
  const [steps, setSteps] = useState(space.subtasks)
  const [notes, setNotes] = useState(space.item.notes ?? '')
  const [noteState, setNoteState] = useState<'saved' | 'saving' | 'unsaved'>('saved')
  const [newStep, setNewStep] = useState('')
  const action = useAction()
  const timer = useRef<number | undefined>(undefined)

  useEffect(() => {
    if (notes === (space.item.notes ?? '')) return
    window.clearTimeout(timer.current)
    timer.current = window.setTimeout(async () => {
      setNoteState('saving')
      try {
        await api.put(`/api/work/${space.item.id}/notes`, { notes })
        setNoteState('saved')
      } catch {
        setNoteState('unsaved')
      }
    }, 900)
    return () => window.clearTimeout(timer.current)
  }, [notes, space.item.id, space.item.notes])

  const breakdown = () =>
    action.run(async () => {
      if (steps.length && !window.confirm('Replace your current steps with a new breakdown?')) return
      const r = await api.post<{ subtasks: Subtask[] }>(`/api/work/${space.item.id}/breakdown${steps.length ? '?replace=true' : ''}`)
      setSteps(r.subtasks)
    })
  const toggle = (s: Subtask) => action.run(async () => { await api.patch(`/api/subtasks/${s.id}`, { done: !s.done }); setSteps(steps.map((x) => (x.id === s.id ? { ...x, done: !x.done } : x))) })
  const remove = (s: Subtask) => action.run(async () => { await api.del(`/api/subtasks/${s.id}`); setSteps(steps.filter((x) => x.id !== s.id)) })
  const add = (e: FormEvent) => {
    e.preventDefault()
    if (!newStep.trim()) return
    action.run(async () => { const s = await api.post<Subtask>(`/api/work/${space.item.id}/subtasks`, { title: newStep.trim() }); setSteps([...steps, s]); setNewStep('') })
  }
  const done = steps.filter((s) => s.done).length

  return (
    <div className="stack" style={{ gap: 22, marginTop: 28 }}>
      <ErrorNote>{action.error}</ErrorNote>
      <section className="panel">
        <div className="panel-head">
          <h3>Steps {steps.length > 0 && <span className="muted mono small">· {done}/{steps.length}</span>}</h3>
          <button className="btn small" type="button" onClick={breakdown} disabled={action.busy}><Sparkles size={13} /> {steps.length ? 'Re-plan steps' : 'Break it down for me'}</button>
        </div>
        {steps.length > 0 && <div style={{ marginBottom: 8 }}><Meter value={done} max={steps.length} tone="ok" /></div>}
        <ul className="checklist">
          {steps.map((s) => (
            <li key={s.id} className={s.done ? 'done' : undefined}>
              <input type="checkbox" checked={s.done} onChange={() => toggle(s)} aria-label={s.title} />
              <span>{s.title}</span>
              {s.minutes && <span className="mono tiny muted">{minutesLabel(s.minutes)}</span>}
              <button className="btn ghost icon small" type="button" aria-label="Remove step" onClick={() => remove(s)}><X size={12} /></button>
            </li>
          ))}
        </ul>
        <form className="row" style={{ gap: 6, marginTop: 6 }} onSubmit={add}>
          <input className="input" value={newStep} onChange={(e) => setNewStep(e.target.value)} placeholder="Add a step" style={{ flex: 1, height: 32 }} />
          <button className="btn small" type="submit"><Plus size={13} /></button>
        </form>
      </section>

      <section className="panel">
        <div className="panel-head"><h3>Your notes and draft</h3><span className="muted tiny">{noteState === 'saved' ? 'Saved' : noteState === 'saving' ? 'Saving…' : 'Not saved yet'}</span></div>
        <textarea className="textarea" rows={6} value={notes} onChange={(e) => { setNotes(e.target.value); setNoteState('unsaved') }} placeholder="Plan, draft or keep links here. Saved to your account; your teacher never sees it." />
      </section>

      <section className="panel">
        <div className="panel-head"><h3>From your materials</h3><Link className="btn ghost small" to="/library">Library</Link></div>
        {space.materials.length === 0 ? <p className="muted small">Nothing in your library matches this assignment yet.</p> : (
          <div className="row" style={{ gap: 6, flexWrap: 'wrap' }}>{space.materials.map((c, i) => <CitationChip key={i} c={c} />)}</div>
        )}
        {space.topics.length > 0 && (
          <p className="small" style={{ marginTop: 10 }}>Topics: {space.topics.map((t, i) => <span key={t.id}>{i > 0 && ', '}<Link to={`/topics/${t.id}`}>{t.title}</Link></span>)}</p>
        )}
      </section>

      {space.sessions.length > 0 && (
        <section>
          <div className="section-head" style={{ marginTop: 0 }}><h2>Focus sessions</h2><span className="aside">{minutesLabel(space.spent_minutes)} so far</span></div>
          {space.sessions.map((s) => (
            <div key={s.id} className="spread small" style={{ padding: '6px 0', borderTop: '1px solid var(--rule)' }}>
              <span>{relative(s.started_at)} · {minutesLabel(Math.round(s.elapsed_seconds / 60))}{s.outcome && ` · “${s.outcome}”`}</span>
              <span className="row" style={{ gap: 6 }}>
                <span className="pill">{s.state}</span>
                {(s.state === 'paused' || s.state === 'active') && <Link className="btn small" to={`/study/${s.id}`}>Resume</Link>}
              </span>
            </div>
          ))}
        </section>
      )}
    </div>
  )
}

export function WorkspaceAside({ space, onItem }: { space: Workspace; onItem: (item: WorkItem) => void }) {
  const navigate = useNavigate()
  const action = useAction()
  const [snoozing, setSnoozing] = useState(false)
  const item = space.item
  const finished = item.status === 'turned_in' || item.status === 'returned'

  const focus = () =>
    action.run(async () => {
      const s = await startSession({ kind: 'assignment', coursework_id: item.id, planned_minutes: Math.min(90, Math.max(25, space.remaining_minutes || 25)) })
      navigate(`/study/${s.id}`)
    })
  const localDone = (done: boolean) => action.run(async () => onItem(await api.post<WorkItem>(`/api/work/${item.id}/local-done`, { done })))
  const snooze = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    const f = new FormData(e.currentTarget)
    action.run(async () => {
      onItem(await api.post<WorkItem>(`/api/work/${item.id}/snooze`, { until: fromLocalInput(String(f.get('until'))), reason: f.get('reason') || null }))
      setSnoozing(false)
    })
  }
  const unsnooze = () => action.run(async () => onItem(await api.del<WorkItem>(`/api/work/${item.id}/snooze`)))
  const confirmDue = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    const value = String(new FormData(e.currentTarget).get('due'))
    action.run(async () => onItem(await api.post<WorkItem>(`/api/work/${item.id}/confirm-due`, { due_at: value ? fromLocalInput(value) : null })))
  }
  const [tomorrow] = useState(() => {
    const d = new Date(Date.now() + 86_400_000)
    d.setHours(9, 0, 0, 0)
    return d
  })

  return (
    <div className="panel stack">
      <ErrorNote>{action.error}</ErrorNote>
      {item.due_confidence === 'inferred' && (
        <form className="note" style={{ flexDirection: 'column', background: 'var(--warn-soft)' }} onSubmit={confirmDue}>
          <strong style={{ fontWeight: 500 }}>Is this deadline right?</strong>
          <span className="small">It was read from text you pasted.</span>
          <input className="input" type="datetime-local" name="due" defaultValue={toLocalInput(item.due_at)} />
          <button className="btn small primary" type="submit"><Check size={13} /> Confirm deadline</button>
        </form>
      )}
      {!finished && !item.local_done_at && (
        <button className="btn primary" type="button" onClick={focus} disabled={action.busy}><Play size={14} /> Start a focus session</button>
      )}
      <div className="small muted">
        {minutesLabel(space.spent_minutes)} spent · about {minutesLabel(space.remaining_minutes)} left
        {space.subtasks.length > 0 && ` · ${space.checklist_done}/${space.subtasks.length} steps`}
      </div>
      {item.source !== 'personal' && !finished && (
        item.local_done_at ? (
          <div className="note ok" style={{ flexDirection: 'column' }}>
            <span className="small">You marked this finished {relative(item.local_done_at)}. {item.source === 'teams' ? 'Teams still shows it as not turned in until you submit there.' : 'Your teacher still needs your turn-in.'}</span>
            <button className="btn small" type="button" onClick={() => localDone(false)}>Undo</button>
          </div>
        ) : (
          <button className="btn" type="button" onClick={() => localDone(true)}>I've finished my part</button>
        )
      )}
      {item.snoozed_until && new Date(item.snoozed_until) > new Date() ? (
        <div className="small">Snoozed until {dueLabel(item.snoozed_until)}{item.snooze_reason && ` · ${item.snooze_reason}`} <button className="btn ghost small" type="button" onClick={unsnooze}>Wake now</button></div>
      ) : !finished && (
        snoozing ? (
          <form className="stack tight" onSubmit={snooze}>
            <input className="input" type="datetime-local" name="until" required defaultValue={toLocalInput(tomorrow.toISOString())} />
            <input className="input" name="reason" placeholder="Why? (optional)" maxLength={200} />
            <button className="btn small" type="submit">Snooze</button>
          </form>
        ) : <button className="btn ghost small" type="button" onClick={() => setSnoozing(true)}><AlarmClockOff size={13} /> Hide from Today until…</button>
      )}
      {space.sources.length > 0 && (
        <p className="muted tiny">Seen in: {space.sources.map((s) => s.provider).join(', ')}{item.last_verified_at && ` · last checked ${relative(item.last_verified_at)}`}</p>
      )}
    </div>
  )
}
