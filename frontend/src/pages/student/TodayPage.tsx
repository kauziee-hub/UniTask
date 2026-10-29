import { useState, type ReactNode } from 'react'
import { AlertTriangle, ArrowRight, Check, Play, RefreshCw } from 'lucide-react'
import { Link, useNavigate } from 'react-router-dom'
import { WorkRow } from '../../components/WorkRow'
import { ErrorNote, Meter, Spinner } from '../../components/ui'
import { api, type Plan } from '../../lib/api'
import { dueLabel, longDate, minutesLabel, relative } from '../../lib/format'
import { startSession } from '../../lib/study'
import type { Home, TimelineRow } from '../../lib/types'
import { useAction } from '../../lib/useAction'
import { useLoad } from '../../lib/useLoad'

const FREE_TIME = [30, 60, 120, 180]
const clock = new Intl.DateTimeFormat(undefined, { hour: 'numeric', minute: '2-digit' })

function FreeTime() {
  const [minutes, setMinutes] = useState<number | null>(null)
  const { data: plan, loading, error } = useLoad<Plan>(minutes ? `/api/plan?minutes=${minutes}` : null)
  return (
    <section className="panel">
      <div className="spread">
        <div>
          <h3>Got a gap between classes?</h3>
          <p className="muted small">Pick how long you have. UniTask fills it with whatever matters most.</p>
        </div>
        <div className="segmented" role="group" aria-label="Free time">
          {FREE_TIME.map((value) => (
            <button key={value} type="button" aria-pressed={minutes === value} onClick={() => setMinutes(value)}>
              {minutesLabel(value)}
            </button>
          ))}
        </div>
      </div>
      {loading && <div style={{ marginTop: 12 }}><Spinner /></div>}
      <ErrorNote>{error}</ErrorNote>
      {plan && !loading && (
        plan.blocks.length === 0 ? (
          <p className="muted" style={{ marginTop: 12 }}>Nothing pending. Take the break.</p>
        ) : (
          <ol className="list plan-steps">
            {plan.blocks.map((block) => (
              <li key={block.item_id}>
                <span>
                  <Link to={`/work/${block.item_id}`} style={{ fontWeight: 500 }}>{block.title}</Link>
                  <span className="muted" style={{ display: 'block', fontSize: 12.5 }}>{block.note}</span>
                </span>
                <span className="mono">{minutesLabel(block.minutes)}{block.finishes_item ? ' · done' : ''}</span>
              </li>
            ))}
          </ol>
        )
      )}
    </section>
  )
}

function DayLine({ rows, now }: { rows: TimelineRow[]; now: Date }) {
  if (rows.length === 0) return <p className="muted small">No classes, study blocks or deadlines today.</p>
  const items: ReactNode[] = []
  let nowShown = false
  rows.forEach((row, index) => {
    const start = new Date(row.start)
    const end = row.end ? new Date(row.end) : start
    if (!nowShown && start > now) {
      nowShown = true
      if (index > 0) items.push(<li key="now" className="now-row" aria-label="Now"><span /></li>)
    }
    const label = { deadline: 'Due', study: 'Study', exam: 'Exam', class: 'Class', lab: 'Lab', tutorial: 'Tutorial' }[row.kind]
    const content = (
      <>
        <span style={{ fontWeight: 500 }}>{row.title}</span>
        <span className="muted tiny" style={{ display: 'block' }}>
          {label}
          {row.end && ` · until ${clock.format(end)}`}
          {row.location && ` · ${row.location}`}
          {row.state && row.state !== 'planned' && ` · ${row.state}`}
          {row.done && ' · done'}
        </span>
      </>
    )
    items.push(
      <li key={`${row.kind}-${index}`} className={end < now ? 'past' : undefined}>
        <span className="t">{clock.format(start)}</span>
        <span className={`mark ${row.kind}`} style={row.color && row.kind !== 'exam' && row.kind !== 'deadline' ? { background: row.color } : undefined} />
        <span>{row.link ? <Link to={row.link} style={{ textDecoration: 'none' }}>{content}</Link> : content}</span>
      </li>,
    )
  })
  return <ul className="day-line">{items}</ul>
}

function Setup({ home, reload }: { home: Home; reload: () => void }) {
  const { busy, error, run } = useAction()
  const s = home.setup
  const steps = [
    { done: s.has_subjects, label: 'Add your subjects', hint: 'And paste each syllabus', to: '/subjects' },
    { done: s.has_timetable, label: 'Add your timetable', hint: 'Type it in or upload a photo', to: '/planner?tab=timetable' },
    { done: s.has_materials, label: 'Upload notes and past papers', hint: 'Search them and ask questions', to: '/library' },
    { done: s.has_exams, label: 'Add your next exam', hint: 'Get a rescue plan', to: '/exams' },
    { done: s.connections.length > 0 || s.has_work, label: 'Bring in deadlines', hint: 'Teams, Moodle, a file or paste text', to: '/connections' },
  ]
  if (steps.every((step) => step.done)) return null
  const loadDemo = () =>
    run(async () => {
      await api.post('/api/demo')
      reload()
    })
  return (
    <section className="panel" style={{ marginBottom: 24 }}>
      <div className="panel-head">
        <h3>Set up your workspace</h3>
        <button className="btn small" type="button" onClick={loadDemo} disabled={busy}>
          {busy ? 'Adding…' : 'Try it with a labelled demo subject'}
        </button>
      </div>
      <ErrorNote>{error}</ErrorNote>
      <div className="setup-steps">
        {steps.map((step) => (
          <Link key={step.label} to={step.to} className={step.done ? 'done' : undefined}>
            {step.done ? <Check size={16} /> : <ArrowRight size={16} />}
            <span>
              <strong style={{ fontWeight: 500 }}>{step.label}</strong>
              <span className="muted tiny" style={{ display: 'block' }}>{step.hint}</span>
            </span>
          </Link>
        ))}
      </div>
    </section>
  )
}

export function TodayPage() {
  const { data, error, loading, reload } = useLoad<Home>('/api/home')
  const navigate = useNavigate()
  const action = useAction()
  const [syncing, setSyncing] = useState(false)

  const go = async () => {
    if (!data) return
    const next = data.next
    if (next.session) {
      const session = await action.run(() => startSession(next.session!))
      if (session) navigate(`/study/${session.id}`)
    } else if (next.to) {
      navigate(next.to)
    }
  }

  const syncTeams = async () => {
    setSyncing(true)
    try {
      await api.post('/api/integrations/teams/sync')
      await reload()
    } finally {
      setSyncing(false)
    }
  }

  const now = new Date()
  return (
    <main className="page wide">
      <p className="kicker">{longDate()}</p>
      <ErrorNote>{error}</ErrorNote>
      {!data && loading && <div style={{ marginTop: 30 }}><Spinner /></div>}
      {data && (
        <>
          <div style={{ height: 14 }} />
          <Setup home={data} reload={reload} />
          <div className="command">
            <div className="stack" style={{ gap: 24 }}>
              <section className="next-action" aria-label="Do this next">
                <p className="kicker">{data.next.kind === 'plan' ? 'Nothing urgent' : 'Do this next'}</p>
                <h2>{data.next.title}</h2>
                <p className="why">{data.next.reason}</p>
                <ErrorNote>{action.error}</ErrorNote>
                <div className="actions">
                  <button className="btn" type="button" onClick={go} disabled={action.busy}>
                    {data.next.session ? <Play size={14} /> : <ArrowRight size={14} />} {data.next.label}
                  </button>
                  {data.next.session && data.next.to && (
                    <Link className="btn ghost" to={data.next.to}>Details</Link>
                  )}
                </div>
              </section>

              {data.warnings.length > 0 && (
                <section className="panel tone-accent">
                  <div className="panel-head"><h3><AlertTriangle size={14} style={{ verticalAlign: -2 }} /> Needs attention</h3></div>
                  <ul className="warn-list">
                    {data.warnings.map((w) => (
                      <li key={w.kind + w.text}>
                        <span>{w.text}</span>
                        <Link className="btn small" to={w.to}>{w.label}</Link>
                      </li>
                    ))}
                  </ul>
                </section>
              )}

              {data.overdue.length > 0 && (
                <section>
                  <div className="section-head" style={{ marginTop: 0 }}>
                    <h2 style={{ color: 'var(--accent)' }}>Overdue, still accepting work</h2>
                    <span className="aside">{data.overdue.length}</span>
                  </div>
                  <ul className="list">{data.overdue.map((item) => <WorkRow key={item.id} item={item} showReason />)}</ul>
                </section>
              )}

              <section>
                <div className="section-head" style={{ marginTop: 0 }}>
                  <h2>Deadline radar · next 14 days</h2>
                  <Link className="aside" to="/work">All deadlines →</Link>
                </div>
                {data.radar.length ? (
                  <ul className="list">{data.radar.map((item) => <WorkRow key={item.id} item={item} showReason />)}</ul>
                ) : (
                  <p className="muted">Nothing due in the next two weeks.</p>
                )}
              </section>

              <FreeTime />
            </div>

            <div className="stack" style={{ gap: 20 }}>
              <section className="panel">
                <div className="panel-head">
                  <h3>Today</h3>
                  <Link className="btn ghost small" to="/planner">Week plan</Link>
                </div>
                <DayLine rows={data.today} now={now} />
              </section>

              {data.exams.length > 0 && (
                <section className="panel">
                  <div className="panel-head"><h3>Exams coming up</h3><Link className="btn ghost small" to="/exams">All</Link></div>
                  <div className="stack">
                    {data.exams.slice(0, 3).map((exam) => (
                      <Link key={exam.id} to={`/exams/${exam.id}`} style={{ textDecoration: 'none' }}>
                        <div className="spread">
                          <strong style={{ fontWeight: 500 }}>{exam.title}</strong>
                          <span className={`mono small${exam.hours_left < 72 ? '' : ' muted'}`} style={exam.hours_left < 72 ? { color: 'var(--accent)' } : undefined}>
                            {relative(exam.starts_at)}
                          </span>
                        </div>
                        <div style={{ margin: '6px 0 2px' }}>
                          <Meter value={exam.covered_count} max={exam.topic_count} tone={exam.covered_count / Math.max(1, exam.topic_count) < 0.5 ? 'accent' : 'ok'} />
                        </div>
                        <span className="muted tiny">
                          {exam.topic_count ? `${exam.covered_count} of ${exam.topic_count} topics revised` : 'No topics yet'} · {dueLabel(exam.starts_at)}
                        </span>
                      </Link>
                    ))}
                  </div>
                </section>
              )}

              <section className="panel">
                <div className="panel-head"><h3>Study queue</h3></div>
                <div className="stack">
                  {data.study.sessions.map((session) => (
                    <div key={session.id} className="spread">
                      <span className="clip">
                        <span className={`pill ${session.state === 'active' ? 'ok' : ''}`}>{session.state === 'active' ? 'Running' : 'Paused'}</span>{' '}
                        {session.title}
                      </span>
                      <Link className="btn small" to={`/study/${session.id}`}>Resume</Link>
                    </div>
                  ))}
                  <div className="spread">
                    <span>{data.study.due_cards ? `${data.study.due_cards} flashcards due` : 'No flashcards due'}</span>
                    <Link className="btn small" to="/revision">{data.study.due_cards ? 'Review' : 'Revision'}</Link>
                  </div>
                  {data.study.weak_topics.map((topic) => (
                    <div key={topic.topic_id} className="spread">
                      <span style={{ minWidth: 0 }}>
                        <Link to={`/topics/${topic.topic_id}`}>{topic.title}</Link>
                        <span className="muted tiny" style={{ display: 'block' }}>Weak: {topic.reason}</span>
                      </span>
                      <Link className="btn small" to={`/tutor?topic=${topic.topic_id}`}>Practise</Link>
                    </div>
                  ))}
                </div>
              </section>

              <section className="panel">
                <div className="panel-head">
                  <h3>Inbox {data.inbox.unread > 0 && <span className="pill accent">{data.inbox.unread} new</span>}</h3>
                  <Link className="btn ghost small" to="/inbox">Open</Link>
                </div>
                {data.inbox.items.length ? (
                  <ul className="list">
                    {data.inbox.items.map((item) => (
                      <li key={item.id} style={{ padding: '6px 0', borderTop: '1px solid var(--rule)' }}>
                        {item.link ? <Link to={item.link} style={{ fontWeight: item.read ? 400 : 550 }}>{item.title}</Link> : <span>{item.title}</span>}
                        <span className="muted tiny" style={{ display: 'block' }}>{relative(item.created_at)}</span>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="muted small">New assignments, moved deadlines and reminders appear here.</p>
                )}
              </section>

              <section className="panel">
                <div className="panel-head"><h3>This week, so far</h3><Link className="btn ghost small" to="/insights">Insights</Link></div>
                <dl className="facts" style={{ margin: 0 }}>
                  <div><dt>Focused</dt><dd className="mono">{minutesLabel(data.progress.minutes_this_week)}</dd></div>
                  <div><dt>Finished</dt><dd className="mono">{data.progress.items_done}</dd></div>
                  <div><dt>Answers right</dt><dd className="mono">{data.progress.answers ? `${data.progress.correct}/${data.progress.answers}` : '–'}</dd></div>
                </dl>
                {data.progress.coverage.map((c) => (
                  <div key={c.course.id} style={{ marginTop: 10 }}>
                    <div className="spread small"><Link to={`/subjects/${c.course.id}`}>{c.course.name}</Link><span className="mono muted">{c.covered}/{c.total} revised</span></div>
                    <Meter value={c.covered} max={c.total} tone="ok" />
                  </div>
                ))}
              </section>
            </div>
          </div>

          <div className="sync-strip">
            {data.teams.status === 'connected' ? (
              <>
                <span className="dot live" />
                <span>Teams connected{data.teams.last_synced_at && <> · last checked {relative(data.teams.last_synced_at)}</>}</span>
                <button className="btn ghost small" type="button" onClick={syncTeams} disabled={syncing} style={{ marginLeft: 'auto' }}>
                  <RefreshCw size={13} className={syncing ? 'spin' : undefined} /> {syncing ? 'Checking…' : 'Check now'}
                </button>
              </>
            ) : (
              <>
                <span className="dot" />
                <span>{data.setup.connections.length ? `Connected: ${data.setup.connections.join(', ')}` : 'No course platform connected yet.'}</span>
                <Link className="btn small" to="/connections" style={{ marginLeft: 'auto' }}>Connections</Link>
              </>
            )}
          </div>
        </>
      )}
    </main>
  )
}
