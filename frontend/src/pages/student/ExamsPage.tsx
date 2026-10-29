import { useState, type FormEvent } from 'react'
import { CalendarPlus, Play, Plus, Siren, Trash2 } from 'lucide-react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { Empty, ErrorNote, Meter, PageHead, Sheet, Spinner } from '../../components/ui'
import { api } from '../../lib/api'
import { dueLabel, fromLocalInput, minutesLabel, relative } from '../../lib/format'
import type { Block, ExamSummary, RescuePlan, Subject, Syllabus, TopicNode } from '../../lib/types'
import { useAction } from '../../lib/useAction'
import { useLoad } from '../../lib/useLoad'
import { StatusPick } from './SubjectPage'
import { startSession } from '../../lib/study'

const MODES = [
  { key: 'tomorrow', label: 'Exam tomorrow', hint: 'Highest value topics only' },
  { key: 'three_day', label: 'Three days', hint: 'Cover most, revise the rest' },
  { key: 'week', label: 'One week', hint: 'Full coverage if it fits' },
  { key: 'zero', label: 'Starting from zero', hint: 'Assume nothing is known' },
  { key: 'weak', label: 'Weak topics only', hint: 'From your answers' },
  { key: 'pyq', label: 'Past papers first', hint: 'Topics asked before' },
] as const

function NewExam({ subjects, preset, onDone }: { subjects: Subject[]; preset?: number; onDone: (e: ExamSummary) => void }) {
  const { busy, error, run } = useAction()
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const f = new FormData(event.currentTarget)
    run(async () =>
      onDone(
        await api.post<ExamSummary>('/api/exams', {
          title: f.get('title'),
          course_id: f.get('course_id') ? Number(f.get('course_id')) : null,
          starts_at: fromLocalInput(String(f.get('starts_at'))),
          duration_minutes: Number(f.get('duration') || 90),
          location: f.get('location') || null,
        }),
      ),
    )
  }
  return (
    <form className="form-grid" onSubmit={submit}>
      <ErrorNote>{error}</ErrorNote>
      <label className="field span-2"><span>Exam</span><input className="input" name="title" required maxLength={200} placeholder="Compiler Design mid-term" /></label>
      <label className="field span-2">
        <span>Subject <span className="hint">· its syllabus becomes the exam's topics</span></span>
        <select className="select" name="course_id" defaultValue={preset ?? ''}>
          <option value="">No subject</option>
          {subjects.map((s) => <option key={s.id} value={s.id}>{s.name}{s.topic_count ? ` · ${s.topic_count} topics` : ' · no syllabus yet'}</option>)}
        </select>
      </label>
      <label className="field"><span>Starts</span><input className="input" name="starts_at" type="datetime-local" required /></label>
      <label className="field"><span>Minutes</span><input className="input" name="duration" type="number" min={10} max={600} defaultValue={90} /></label>
      <label className="field span-2"><span>Where <span className="hint">· optional</span></span><input className="input" name="location" maxLength={120} /></label>
      <button className="btn primary span-2" type="submit" disabled={busy}>{busy ? 'Saving…' : 'Add exam'}</button>
    </form>
  )
}

export function ExamsPage() {
  const [params] = useSearchParams()
  const preset = params.get('new') ? Number(params.get('new')) : undefined
  const [adding, setAdding] = useState(preset !== undefined)
  const { data, error, loading } = useLoad<ExamSummary[]>('/api/exams')
  const { data: subjects } = useLoad<Subject[]>('/api/subjects')
  const navigate = useNavigate()
  return (
    <main className="page">
      <PageHead kicker="Exam rescue" title="Exams">
        <button className="btn primary" type="button" onClick={() => setAdding(true)}><Plus size={15} /> Add exam</button>
      </PageHead>
      <ErrorNote>{error}</ErrorNote>
      {loading && !data && <Spinner />}
      {data && data.length === 0 && <Empty title="No exams coming up">Add one and UniTask works out what to study in the time you actually have, using your syllabus, past papers and answers.</Empty>}
      <div className="stack">
        {data?.map((exam) => (
          <Link key={exam.id} to={`/exams/${exam.id}`} className="panel" style={{ textDecoration: 'none' }}>
            <div className="spread">
              <div>
                <p className="kicker" style={{ color: exam.course?.color }}>{exam.course?.name ?? 'No subject'}</p>
                <h3 style={{ fontSize: 18, marginTop: 4 }}>{exam.title}</h3>
              </div>
              <div style={{ textAlign: 'right' }}>
                <span className="mono" style={{ color: exam.hours_left < 72 ? 'var(--accent)' : undefined }}>{relative(exam.starts_at)}</span>
                <span className="muted tiny" style={{ display: 'block' }}>{dueLabel(exam.starts_at)}</span>
              </div>
            </div>
            <div style={{ marginTop: 12 }}><Meter value={exam.covered_count} max={exam.topic_count} tone={exam.covered_count / Math.max(exam.topic_count, 1) < 0.5 ? 'accent' : 'ok'} /></div>
            <p className="muted small" style={{ marginTop: 6 }}>
              {exam.topic_count ? `${exam.covered_count} of ${exam.topic_count} topics revised` : 'No topics yet'} · {exam.planned_blocks} study blocks planned
            </p>
          </Link>
        ))}
      </div>
      <Sheet open={adding} title="Add an exam" onClose={() => setAdding(false)}>
        <NewExam subjects={subjects ?? []} preset={preset} onDone={(e) => navigate(`/exams/${e.id}`)} />
      </Sheet>
    </main>
  )
}

interface ExamDetail extends ExamSummary {
  topics: TopicNode[]
  blocks: Block[]
}

function TopicChooser({ exam, onSaved }: { exam: ExamDetail; onSaved: () => void }) {
  const { data } = useLoad<Syllabus>(exam.course ? `/api/subjects/${exam.course.id}/syllabus` : null)
  const [chosen, setChosen] = useState<Set<number>>(new Set(exam.topics.map((t) => t.id)))
  const { busy, error, run } = useAction()
  if (!exam.course) return <p className="muted small">Link this exam to a subject with a syllabus to choose topics.</p>
  if (!data) return <Spinner />
  const leaves = data.modules.flatMap((m) => (m.topics?.length ? m.topics : [m]))
  const toggle = (id: number) => setChosen((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n })
  return (
    <div className="stack">
      <ErrorNote>{error}</ErrorNote>
      <div style={{ maxHeight: 320, overflowY: 'auto' }}>
        {data.modules.map((m) => (
          <div key={m.id} style={{ marginBottom: 10 }}>
            <p className="kicker">{m.title}</p>
            {(m.topics?.length ? m.topics : [m]).map((t) => (
              <label key={t.id} className="check" style={{ display: 'flex', padding: '3px 0' }}>
                <input type="checkbox" checked={chosen.has(t.id)} onChange={() => toggle(t.id)} /> {t.title}
              </label>
            ))}
          </div>
        ))}
      </div>
      <div className="row" style={{ gap: 8 }}>
        <button className="btn primary small" type="button" disabled={busy} onClick={() => run(async () => { await api.put(`/api/exams/${exam.id}/topics`, { topic_ids: [...chosen] }); onSaved() })}>Save {chosen.size} topics</button>
        <button className="btn small" type="button" onClick={() => setChosen(new Set(leaves.map((t) => t.id)))}>All</button>
        <button className="btn small" type="button" onClick={() => setChosen(new Set())}>None</button>
      </div>
    </div>
  )
}

export function ExamPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const { data: exam, error, reload } = useLoad<ExamDetail>(`/api/exams/${id}`)
  const [mode, setMode] = useState<(typeof MODES)[number]['key']>('three_day')
  const [hours, setHours] = useState('')
  const [plan, setPlan] = useState<RescuePlan | null>(null)
  const [choosing, setChoosing] = useState(false)
  const action = useAction()

  if (!exam) return <main className="page">{error ? <ErrorNote>{error}</ErrorNote> : <Spinner />}</main>

  const body = () => ({ mode, hours: hours ? Number(hours) : null })
  const build = () => action.run(async () => setPlan(await api.post<RescuePlan>(`/api/exams/${exam.id}/rescue`, body())))
  const apply = () =>
    action.run(async () => {
      setPlan(await api.post<RescuePlan>(`/api/exams/${exam.id}/rescue/apply`, body()))
      await reload()
    })
  const study = (topicId: number, minutes: number) =>
    action.run(async () => {
      const session = await startSession({ kind: 'rescue', topic_id: topicId, exam_id: exam.id, planned_minutes: Math.min(240, minutes) })
      navigate(`/study/${session.id}`)
    })
  const setStatus = (topic: TopicNode, status: TopicNode['status']) => action.run(async () => { await api.patch(`/api/topics/${topic.id}`, { status }); await reload() })
  const remove = async () => {
    if (!window.confirm('Delete this exam and its planned study blocks?')) return
    await api.del(`/api/exams/${exam.id}`)
    navigate('/exams')
  }

  const chosenPct = plan ? Math.round((100 * plan.chosen_minutes) / Math.max(plan.needed_minutes, plan.chosen_minutes, 1)) : 0
  const upcomingBlocks = exam.blocks.filter((b) => b.state === 'planned' && new Date(b.ends_at) > new Date())

  return (
    <main className="page wide">
      <nav className="crumbs"><Link to="/exams">Exams</Link>{exam.course && <><span>/</span><Link to={`/subjects/${exam.course.id}`}>{exam.course.name}</Link></>}</nav>
      <header className="page-head">
        <div>
          <p className="kicker" style={{ color: exam.hours_left < 72 ? 'var(--accent)' : undefined }}>{relative(exam.starts_at)} · {dueLabel(exam.starts_at)}{exam.location && ` · ${exam.location}`}</p>
          <h1 className="title page-title">{exam.title}</h1>
        </div>
        <button className="btn ghost danger" type="button" onClick={remove}><Trash2 size={14} /> Delete</button>
      </header>
      <ErrorNote>{action.error}</ErrorNote>

      <div className="split">
        <div className="stack" style={{ gap: 22 }}>
          <section className="panel stack">
            <div className="spread"><h3><Siren size={14} style={{ verticalAlign: -2 }} /> Rescue plan</h3><span className="muted small">uses your free time before the exam</span></div>
            <div className="mode-pick" role="group" aria-label="Situation">
              {MODES.map((m) => (
                <button key={m.key} type="button" aria-pressed={mode === m.key} onClick={() => setMode(m.key)}>{m.label}<small>{m.hint}</small></button>
              ))}
            </div>
            <div className="row" style={{ gap: 10, flexWrap: 'wrap' }}>
              <label className="row small" style={{ gap: 6 }}>
                I have
                <input className="input" type="number" min={0.5} max={300} step={0.5} value={hours} onChange={(e) => setHours(e.target.value)} placeholder="auto" style={{ width: 80, height: 32 }} />
                hours
              </label>
              <span className="muted tiny">Leave empty to use your real free time (classes, sleep and daily limit taken out).</span>
            </div>
            <button className="btn primary" type="button" onClick={build} disabled={action.busy || exam.topic_count === 0}>{action.busy ? 'Working it out…' : 'Build my rescue plan'}</button>
            {exam.topic_count === 0 && <p className="small" style={{ color: 'var(--accent)' }}>This exam has no topics yet. Add a syllabus to its subject or choose topics.</p>}
          </section>

          {plan && (
            <section className="stack" style={{ gap: 14 }}>
              <div className="budget" aria-label={`${plan.chosen_minutes} minutes planned of ${plan.needed_minutes} needed`}>
                <span className="chosen" style={{ width: `${chosenPct}%` }}>{minutesLabel(plan.chosen_minutes)} planned</span>
                {!plan.feasible && <span className="left-out" style={{ flex: 1 }}>{minutesLabel(Math.max(0, plan.needed_minutes - plan.chosen_minutes))} left out</span>}
              </div>
              <p>{plan.message}</p>
              <p className="muted small">Budget {minutesLabel(plan.budget_minutes)} · free before the exam {minutesLabel(plan.free_minutes)} · everything would need {minutesLabel(plan.needed_minutes)}. Past-paper counts are history, not predictions.</p>
              <div>
                {plan.chosen.map((step) => (
                  <div key={step.topic_id} className="rescue-step">
                    <span className="n">{step.order}</span>
                    <div style={{ minWidth: 0 }}>
                      <Link to={`/topics/${step.topic_id}`} style={{ fontWeight: 500 }}>{step.title}</Link>
                      <span className="muted tiny" style={{ display: 'block' }}>{step.module} · {step.reason}</span>
                      {step.materials.length > 0 ? (
                        <div className="row" style={{ gap: 6, flexWrap: 'wrap', marginTop: 6 }}>
                          {step.materials.map((m, i) => <Link key={i} className="cite" to={`/library/${m.material_id}?page=${m.page}`}>{m.title} · p.{m.page}</Link>)}
                        </div>
                      ) : <span className="tiny" style={{ color: 'var(--warn)' }}>No notes for this topic in your library.</span>}
                    </div>
                    <div style={{ textAlign: 'right' }}>
                      <span className="mono small">{minutesLabel(step.minutes)}</span>
                      <button className="btn small" type="button" style={{ display: 'flex', marginTop: 6 }} onClick={() => study(step.topic_id, step.minutes)}><Play size={12} /> Start</button>
                    </div>
                  </div>
                ))}
              </div>
              {plan.excluded.length > 0 && (
                <details className="panel">
                  <summary style={{ cursor: 'pointer' }}>Left out ({plan.excluded.length}) and why</summary>
                  {plan.excluded.map((t) => <p key={t.topic_id} className="small" style={{ marginTop: 6 }}><strong style={{ fontWeight: 500 }}>{t.title}</strong> · {minutesLabel(t.minutes)} · <span className="muted">{t.reason}</span></p>)}
                </details>
              )}
              {plan.schedule.length > 0 && (
                <div className="panel">
                  <div className="spread"><h3>When</h3>
                    {plan.applied === undefined ? (
                      <button className="btn primary small" type="button" onClick={apply} disabled={action.busy}><CalendarPlus size={13} /> Put these in my planner</button>
                    ) : <span className="pill ok">{plan.applied} blocks added to your planner</span>}
                  </div>
                  {plan.schedule.map((s, i) => <p key={i} className="small" style={{ marginTop: 6 }}><span className="mono">{dueLabel(s.starts_at)}</span> · {s.title}</p>)}
                  {plan.unscheduled.length > 0 && <p className="small" style={{ marginTop: 8, color: 'var(--accent)' }}>No free slot left for: {plan.unscheduled.join(', ')}</p>}
                </div>
              )}
            </section>
          )}
        </div>

        <aside className="stack">
          <div className="panel">
            <div className="spread"><h3>Topics ({exam.covered_count}/{exam.topic_count} revised)</h3><button className="btn ghost small" type="button" onClick={() => setChoosing(true)}>Choose</button></div>
            <p className="muted tiny" style={{ margin: '4px 0 8px' }}>{exam.explicit_topics ? 'Chosen for this exam.' : 'Whole syllabus of the subject.'}</p>
            <div className="stack tight">
              {exam.topics.map((t) => (
                <div key={t.id} className="pick-row small">
                  <Link to={`/topics/${t.id}`} className="clip" title={t.title}>{t.title}</Link>
                  <StatusPick topic={t} onChange={(s) => setStatus(t, s)} />
                </div>
              ))}
            </div>
          </div>
          {upcomingBlocks.length > 0 && (
            <div className="panel">
              <h3>Planned study</h3>
              {upcomingBlocks.map((b) => <p key={b.id} className="small" style={{ marginTop: 6 }}><span className="mono">{dueLabel(b.starts_at)}</span> · {b.title}</p>)}
              <Link className="btn small" to="/planner" style={{ marginTop: 10 }}>Open planner</Link>
            </div>
          )}
        </aside>
      </div>
      <Sheet open={choosing} title="Topics in this exam" onClose={() => setChoosing(false)}>
        <TopicChooser exam={exam} onSaved={() => { setChoosing(false); void reload() }} />
      </Sheet>
    </main>
  )
}
