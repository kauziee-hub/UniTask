import { useState, type FormEvent } from 'react'
import { Check, Download, ImageUp, Play, Plus, RefreshCw, SkipForward, Trash2 } from 'lucide-react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { Empty, ErrorNote, PageHead, Sheet, Spinner, Tabs } from '../../components/ui'
import { api, apiUrl, downloadFile, type CourseBrief } from '../../lib/api'
import { dueLabel, minutesLabel } from '../../lib/format'
import type { Block, Planner, Subject, TimetableEntry } from '../../lib/types'
import { useAction } from '../../lib/useAction'
import { useLoad } from '../../lib/useLoad'
import { startSession } from '../../lib/study'

const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
const time = new Intl.DateTimeFormat(undefined, { hour: 'numeric', minute: '2-digit' })
const dayFmt = new Intl.DateTimeFormat(undefined, { weekday: 'short', day: 'numeric' })

function hm(value: string) {
  const [h, m] = value.split(':').map(Number)
  return h * 60 + m
}

function localKey(date: Date) {
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

function Week({ planner, onBlock }: { planner: Planner; onBlock: (b: Block) => void }) {
  const startMin = Math.min(hm(planner.day_start), 8 * 60)
  const endMin = Math.max(hm(planner.day_end), 18 * 60)
  const span = endMin - startMin
  const first = new Date(planner.window.start)
  const days = Array.from({ length: 7 }, (_, i) => new Date(first.getFullYear(), first.getMonth(), first.getDate() + i))
  const now = new Date()
  const pos = (d: Date) => ((d.getHours() * 60 + d.getMinutes() - startMin) / span) * 100
  const hours = Array.from({ length: Math.floor(span / 60) + 1 }, (_, i) => startMin + i * 60).filter((m) => m <= endMin)

  return (
    <div className="week" role="grid" aria-label="Week plan">
      <div className="corner" />
      {days.map((d) => {
        const key = localKey(d)
        const load = planner.forecast.load[key] ?? 0
        return (
          <div key={key} className={`head${key === localKey(now) ? ' today' : ''}`}>
            {dayFmt.format(d)}
            <span className="load">{load ? `${minutesLabel(load)} planned` : '—'}</span>
          </div>
        )
      })}
      <div className="hours">
        {hours.map((m) => <span key={m} className="hour" style={{ top: `${((m - startMin) / span) * 100}%` }}>{String(Math.floor(m / 60)).padStart(2, '0')}</span>)}
      </div>
      {days.map((d) => {
        const key = localKey(d)
        const sameDay = (iso: string) => localKey(new Date(iso)) === key
        return (
          <div key={key} className="col">
            {hours.map((m) => <span key={m} className="hour" style={{ top: `${((m - startMin) / span) * 100}%` }} aria-hidden="true" />)}
            {planner.busy.filter((b) => sameDay(b.starts_at)).map((b, i) => {
              const s = new Date(b.starts_at)
              const e = new Date(b.ends_at)
              return (
                <div key={`busy-${i}`} className={`ev ${b.kind}`} style={{ top: `${pos(s)}%`, height: `${Math.max(2.5, pos(e) - pos(s))}%` }} title={`${b.title} ${time.format(s)}–${time.format(e)}`}>
                  <span className="t">{time.format(s)}</span>{b.title}
                </div>
              )
            })}
            {planner.blocks.filter((b) => sameDay(b.starts_at)).map((b) => {
              const s = new Date(b.starts_at)
              const e = new Date(b.ends_at)
              return (
                <button key={b.id} type="button" className={`ev ${b.kind} ${b.state}`} style={{ top: `${pos(s)}%`, height: `${Math.max(2.5, pos(e) - pos(s))}%` }} onClick={() => onBlock(b)} title={b.reason ?? b.title}>
                  <span className="t">{time.format(s)} · {b.minutes}m</span>{b.title}
                </button>
              )
            })}
            {key === localKey(now) && pos(now) >= 0 && pos(now) <= 100 && <span className="now" style={{ top: `${pos(now)}%` }} />}
          </div>
        )
      })}
    </div>
  )
}

function BlockSheet({ block, onClose, onChanged }: { block: Block | null; onClose: () => void; onChanged: () => void }) {
  const navigate = useNavigate()
  const { busy, error, run } = useAction()
  if (!block) return null
  const state = (s: Block['state']) => run(async () => { await api.patch(`/api/planner/blocks/${block.id}`, { state: s }); onChanged(); onClose() })
  const start = () =>
    run(async () => {
      const session = await startSession({
        kind: block.kind === 'rescue' ? 'rescue' : block.coursework_id ? 'assignment' : block.kind === 'revision' ? 'revision' : 'topic',
        coursework_id: block.coursework_id,
        topic_id: block.topic_id,
        exam_id: block.exam_id,
        plan_block_id: block.id,
        planned_minutes: block.minutes,
        title: block.title,
      })
      navigate(`/study/${session.id}`)
    })
  return (
    <div className="stack">
      <p className="mono small">{dueLabel(block.starts_at)} – {time.format(new Date(block.ends_at))} · {minutesLabel(block.minutes)}</p>
      {block.reason && <p className="muted">{block.reason}</p>}
      <ErrorNote>{error}</ErrorNote>
      <button className="btn primary" type="button" onClick={start} disabled={busy}><Play size={14} /> Start this now</button>
      <div className="row" style={{ gap: 8 }}>
        <button className="btn" type="button" onClick={() => state('done')} disabled={busy}><Check size={14} /> Done</button>
        <button className="btn" type="button" onClick={() => state('skipped')} disabled={busy}><SkipForward size={14} /> Skip</button>
        <button className="btn ghost danger" type="button" onClick={() => run(async () => { await api.del(`/api/planner/blocks/${block.id}`); onChanged(); onClose() })}><Trash2 size={14} /></button>
      </div>
      {block.coursework_id && <Link to={`/work/${block.coursework_id}`}>Open the assignment →</Link>}
      {block.exam_id && <Link to={`/exams/${block.exam_id}`}>Open the exam →</Link>}
      {block.topic_id && <Link to={`/topics/${block.topic_id}`}>Open the topic →</Link>}
    </div>
  )
}

function WeekTab() {
  const { data, setData, error, loading, reload } = useLoad<Planner>('/api/planner?days=7')
  const [block, setBlock] = useState<Block | null>(null)
  const { busy, error: actionError, run } = useAction()
  const [note, setNote] = useState<string | null>(null)
  const replan = () =>
    run(async () => {
      const result = await api.post<Planner>('/api/planner/replan', { days: 7 })
      setData(result)
      setNote(`Plan rebuilt: ${result.created} blocks placed${result.marked_missed ? `, ${result.marked_missed} missed block${result.marked_missed > 1 ? 's' : ''} recorded` : ''}.`)
    })
  if (!data) return loading ? <Spinner /> : <ErrorNote>{error}</ErrorNote>
  const tight = data.demands.filter((d) => data.forecast.risk[d.key] === 'tight')
  return (
    <div className="stack" style={{ gap: 18 }}>
      <div className="row" style={{ gap: 10, flexWrap: 'wrap' }}>
        <button className="btn primary" type="button" onClick={replan} disabled={busy}><RefreshCw size={14} className={busy ? 'spin' : undefined} /> {data.blocks.length ? 'Replan from now' : 'Plan my week'}</button>
        <span className="muted small">Fits work into free time between {data.day_start} and {data.day_end}, at most {minutesLabel(data.daily_cap)} a day, never after a deadline. <Link to="/settings">Change</Link></span>
      </div>
      <ErrorNote>{actionError}</ErrorNote>
      {note && <div className="note ok">{note}</div>}
      {!data.has_timetable && <div className="note">Add your timetable so study blocks don't land on top of classes. <Link to="/planner?tab=timetable">Add timetable</Link></div>}
      {data.forecast.unfit.length > 0 && (
        <div className="panel tone-accent">
          <h3>Won't fit before the deadline</h3>
          {data.forecast.unfit.map((u) => (
            <p key={u.key} className="small" style={{ marginTop: 6 }}>
              {u.coursework_id ? <Link to={`/work/${u.coursework_id}`}>{u.title}</Link> : u.exam_id ? <Link to={`/exams/${u.exam_id}`}>{u.title}</Link> : u.title}
              {' · '}<span className="muted">{u.reason}{u.estimated && ' (time estimated — set the real effort on the assignment)'}</span>
            </p>
          ))}
          <p className="small muted" style={{ marginTop: 8 }}>Options: raise your daily limit in Settings, snooze something less important, or use Exam Rescue to cut scope.</p>
        </div>
      )}
      {tight.length > 0 && <p className="small" style={{ color: 'var(--warn)' }}>Tight (finishes within 12 hours of the deadline): {tight.map((d) => d.title).join(', ')}</p>}
      <Week planner={data} onBlock={setBlock} />
      <div className="legend">
        <span><i style={{ background: 'var(--sunken)', borderLeft: '3px solid var(--muted)' }} /> Class</span>
        <span><i style={{ background: 'var(--study-soft)', borderLeft: '3px solid var(--study)' }} /> Planned study</span>
        <span><i style={{ background: 'var(--warn-soft)', borderLeft: '3px solid var(--warn)' }} /> Exam rescue</span>
        <span><i style={{ background: 'var(--accent-soft)', borderLeft: '3px solid var(--accent)' }} /> Exam</span>
        <span><i style={{ outline: '1px dashed var(--accent)' }} /> Missed</span>
      </div>
      {data.conflicts.length > 0 && (
        <div className="note error">
          Clashes: {data.conflicts.map((c, i) => <span key={i}>{i > 0 && '; '}{c.a} and {c.b} ({dueLabel(c.start)})</span>)}
        </div>
      )}
      <Sheet open={Boolean(block)} title={block?.title ?? ''} onClose={() => setBlock(null)}>
        <BlockSheet block={block} onClose={() => setBlock(null)} onChanged={reload} />
      </Sheet>
    </div>
  )
}

function TimetableTab() {
  const { data, setData, error, reload } = useLoad<{ entries: TimetableEntry[]; unconfirmed: number; conflicts: Planner['conflicts'] }>('/api/timetable')
  const { data: subjects } = useLoad<Subject[]>('/api/subjects')
  const { data: images, reload: reloadImages } = useLoad<{ id: string; original_filename: string; file_url: string; uploaded_at: string }[]>('/api/timetables')
  const { busy, error: actionError, run } = useAction()
  const [message, setMessage] = useState<string | null>(null)

  const add = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const form = event.currentTarget
    const f = new FormData(form)
    run(async () => {
      await api.post('/api/timetable', {
        title: f.get('title'),
        course_id: f.get('course_id') ? Number(f.get('course_id')) : null,
        weekday: Number(f.get('weekday')),
        start: f.get('start'),
        end: f.get('end'),
        kind: f.get('kind'),
        location: f.get('location') || null,
      })
      form.reset()
      await reload()
    })
  }
  const extract = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const form = event.currentTarget
    run(async () => {
      const result = await api.post<{ message: string }>('/api/timetable/extract', new FormData(form))
      setMessage(result.message)
      form.reset()
      await reload()
      await reloadImages()
    })
  }
  const confirmAll = (discard: boolean) => run(async () => setData(await api.post(`/api/timetable/confirm-all${discard ? '?discard=true' : ''}`)))
  const remove = (id: number) => run(async () => { await api.del(`/api/timetable/${id}`); await reload() })
  const confirmOne = (id: number) => run(async () => { await api.patch(`/api/timetable/${id}`, { confirmed: true }); await reload() })

  return (
    <div className="split">
      <div className="stack">
        <ErrorNote>{error ?? actionError}</ErrorNote>
        {message && <div className="note ok">{message}</div>}
        {data && data.unconfirmed > 0 && (
          <div className="note" style={{ background: 'var(--warn-soft)', flexWrap: 'wrap', alignItems: 'center' }}>
            <span style={{ flex: 1 }}>{data.unconfirmed} classes were read from your image. They don't affect planning until you confirm them.</span>
            <button className="btn small primary" type="button" onClick={() => confirmAll(false)}>Confirm all</button>
            <button className="btn small" type="button" onClick={() => confirmAll(true)}>Discard</button>
          </div>
        )}
        {data?.conflicts.length ? <div className="note error">Clash: {data.conflicts.map((c) => `${c.a} / ${c.b}`).join('; ')}</div> : null}
        {data && data.entries.length === 0 && <Empty title="No classes yet">Add them below, or upload a photo or screenshot of your timetable.</Empty>}
        {DAYS.map((day, index) => {
          const rows = (data?.entries ?? []).filter((e) => e.weekday === index)
          if (!rows.length) return null
          return (
            <section key={day}>
              <p className="kicker" style={{ marginTop: 8 }}>{day}</p>
              {rows.map((e) => (
                <div key={e.id} className="material-row" style={{ gridTemplateColumns: '90px minmax(0,1fr) auto', background: e.confirmed ? undefined : 'var(--warn-soft)' }}>
                  <span className="mono small">{e.start}–{e.end}</span>
                  <span className="clip">{e.title} <span className="muted tiny">· {e.kind}{e.location && ` · ${e.location}`}{e.course && ` · ${e.course.name}`}{e.source === 'image' && ' · from image'}</span></span>
                  <span className="row" style={{ gap: 4 }}>
                    {!e.confirmed && <button className="btn ghost small" type="button" onClick={() => confirmOne(e.id)}>Confirm</button>}
                    <button className="btn ghost icon small" type="button" aria-label="Remove" onClick={() => remove(e.id)}><Trash2 size={13} /></button>
                  </span>
                </div>
              ))}
            </section>
          )
        })}
      </div>
      <aside className="stack">
        <form className="panel form-grid" onSubmit={add}>
          <h3 className="span-2">Add a class</h3>
          <label className="field span-2"><span>Name</span><input className="input" name="title" required maxLength={160} /></label>
          <label className="field span-2"><span>Subject</span>
            <select className="select" name="course_id" defaultValue=""><option value="">—</option>{subjects?.map((s: CourseBrief) => <option key={s.id} value={s.id}>{s.name}</option>)}</select>
          </label>
          <label className="field"><span>Day</span><select className="select" name="weekday">{DAYS.map((d, i) => <option key={d} value={i}>{d}</option>)}</select></label>
          <label className="field"><span>Type</span><select className="select" name="kind"><option value="class">Class</option><option value="lab">Lab</option><option value="tutorial">Tutorial</option></select></label>
          <label className="field"><span>Starts</span><input className="input" name="start" type="time" required /></label>
          <label className="field"><span>Ends</span><input className="input" name="end" type="time" required /></label>
          <label className="field span-2"><span>Room <span className="hint">· optional</span></span><input className="input" name="location" maxLength={80} /></label>
          <button className="btn primary span-2" type="submit" disabled={busy}><Plus size={14} /> Add</button>
        </form>
        <form className="panel stack" onSubmit={extract}>
          <h3>From a photo or screenshot</h3>
          <p className="muted small">Stored privately{images && images.length ? '' : ''}. The classes it reads are shown for you to check before they count.</p>
          <input name="file" type="file" accept="image/png,image/jpeg,image/webp" required />
          <button className="btn" type="submit" disabled={busy}><ImageUp size={14} /> {busy ? 'Reading…' : 'Upload and read'}</button>
          {images && images.length > 0 && (
            <div className="row" style={{ gap: 6, flexWrap: 'wrap' }}>
              {images.slice(0, 4).map((img) => (
                <a key={img.id} href={apiUrl(img.file_url)} target="_blank" rel="noreferrer" title={img.original_filename}>
                  <img src={apiUrl(img.file_url)} alt={img.original_filename} style={{ width: 72, height: 54, objectFit: 'cover', borderRadius: 6, border: '1px solid var(--rule)' }} />
                </a>
              ))}
            </div>
          )}
        </form>
      </aside>
    </div>
  )
}

interface AttendanceData {
  threshold: number | null
  note: string
  subjects: { course: CourseBrief; present: number; total: number; percent: number | null; can_miss: number | null; must_attend: number | null; marks: { id: number; date: string; present: boolean }[] }[]
}

function AttendanceTab() {
  const { data, setData, error } = useLoad<AttendanceData>('/api/attendance')
  const { data: subjects } = useLoad<Subject[]>('/api/subjects')
  const [day, setDay] = useState(localKey(new Date()))
  const { error: actionError, run } = useAction()
  const mark = (course: number, present: boolean) => run(async () => setData(await api.post<AttendanceData>('/api/attendance', { course_id: course, date: day, present })))
  const rows = new Map((data?.subjects ?? []).map((s) => [s.course.id, s]))
  return (
    <div className="stack">
      <ErrorNote>{error ?? actionError}</ErrorNote>
      <p className="muted">{data?.note} {data?.threshold ? `Your rule: ${data.threshold}%.` : <>Set your university's minimum in <Link to="/settings">Settings</Link> to see how many classes you can miss.</>}</p>
      <label className="row small" style={{ gap: 8 }}>Marking for <input className="input" type="date" value={day} onChange={(e) => setDay(e.target.value)} style={{ width: 170 }} /></label>
      {(subjects ?? []).map((s) => {
        const row = rows.get(s.id)
        const today = row?.marks.find((m) => m.date === day)
        return (
          <div key={s.id} className="panel">
            <div className="spread">
              <div>
                <strong style={{ fontWeight: 500 }}>{s.name}</strong>
                <span className="muted small" style={{ display: 'block' }}>
                  {row && row.total ? `${row.present}/${row.total} attended · ${row.percent}%` : 'No classes recorded'}
                  {row?.can_miss != null && ` · you can miss ${row.can_miss} more and stay above ${data?.threshold}%`}
                  {row?.must_attend != null && <span style={{ color: 'var(--accent)' }}>{` · attend the next ${row.must_attend} to get back to ${data?.threshold}%`}</span>}
                </span>
              </div>
              <div className="row" style={{ gap: 6 }}>
                <button className="btn small" type="button" aria-pressed={today?.present === true} style={today?.present === true ? { background: 'var(--ok-soft)' } : undefined} onClick={() => mark(s.id, true)}>Present</button>
                <button className="btn small" type="button" aria-pressed={today?.present === false} style={today?.present === false ? { background: 'var(--accent-soft)' } : undefined} onClick={() => mark(s.id, false)}>Absent</button>
              </div>
            </div>
          </div>
        )
      })}
    </div>
  )
}

export function PlannerPage() {
  const [params, setParams] = useSearchParams()
  const tab = (params.get('tab') as 'week' | 'timetable' | 'attendance') ?? 'week'
  const { error, run } = useAction()
  return (
    <main className="page wide">
      <PageHead kicker="Study planner" title="Your week">
        <button className="btn" type="button" onClick={() => run(() => downloadFile('/api/calendar/export.ics', 'unitask.ics'))}><Download size={14} /> Export to calendar</button>
      </PageHead>
      <ErrorNote>{error}</ErrorNote>
      <Tabs value={tab} onChange={(t) => setParams({ tab: t })} tabs={[{ key: 'week', label: 'Week plan' }, { key: 'timetable', label: 'Timetable' }, { key: 'attendance', label: 'Attendance' }]} />
      {tab === 'week' && <WeekTab />}
      {tab === 'timetable' && <TimetableTab />}
      {tab === 'attendance' && <AttendanceTab />}
    </main>
  )
}
