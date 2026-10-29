import { Link } from 'react-router-dom'
import { Empty, ErrorNote, PageHead, Spinner } from '../../components/ui'
import type { CourseBrief } from '../../lib/api'
import { minutesLabel, shortDate } from '../../lib/format'
import { useLoad } from '../../lib/useLoad'
import { CoverageBar } from './SubjectsPage'

interface Insights {
  study_minutes: { date: string; minutes: number }[]
  completions: { date: string; count: number }[]
  on_time: { done: number; on_time: number; rate: number | null }
  workload: { date: string; minutes: number; items: number; exams: number }[]
  coverage: { course: CourseBrief; not_started: number; in_progress: number; revised: number; practised: number; total: number }[]
  topic_accuracy: { topic_id: number; title: string; course: CourseBrief | null; attempts: number; correct: number; rate: number }[]
  actions: { text: string; label: string; to: string }[]
}

const weekday = new Intl.DateTimeFormat(undefined, { weekday: 'narrow' })

/** One series of vertical bars on a zero baseline, with a hover title per bar and an optional reference line. */
function Bars({ rows, tone = 'bar', cap, unit }: { rows: { label: string; value: number; title: string; tone?: string }[]; tone?: string; cap?: number; unit: (v: number) => string }) {
  const width = 560
  const height = 150
  const pad = { top: 14, bottom: 22, left: 4, right: 4 }
  const max = Math.max(1, cap ?? 0, ...rows.map((r) => r.value))
  const slot = (width - pad.left - pad.right) / rows.length
  const barW = Math.max(4, Math.min(28, slot - 2))
  const y = (v: number) => pad.top + (height - pad.top - pad.bottom) * (1 - v / max)
  const peak = rows.reduce((best, r, i) => (r.value > (rows[best]?.value ?? -1) ? i : best), 0)
  return (
    <svg className="chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label={rows.map((r) => `${r.title}: ${unit(r.value)}`).join('; ')}>
      <line className="axis" x1={pad.left} x2={width - pad.right} y1={height - pad.bottom} y2={height - pad.bottom} />
      {cap !== undefined && <line className="cap" x1={pad.left} x2={width - pad.right} y1={y(cap)} y2={y(cap)}><title>Your daily limit: {unit(cap)}</title></line>}
      {rows.map((r, i) => {
        const x = pad.left + i * slot + (slot - barW) / 2
        const top = y(r.value)
        const h = height - pad.bottom - top
        return (
          <g key={r.label + i}>
            <rect x={pad.left + i * slot} y={pad.top} width={slot} height={height - pad.top - pad.bottom} fill="transparent"><title>{r.title}: {unit(r.value)}</title></rect>
            {r.value > 0 && <path className={`bar ${r.tone ?? tone}`} d={`M${x},${height - pad.bottom} V${top + Math.min(4, h)} q0,-4 4,-4 h${barW - 8} q4,0 4,4 V${height - pad.bottom} Z`} pointerEvents="none" />}
            <text x={x + barW / 2} y={height - 6} textAnchor="middle">{r.label}</text>
            {i === peak && r.value > 0 && <text x={x + barW / 2} y={top - 4} textAnchor="middle" style={{ fill: 'var(--ink)' }}>{unit(r.value)}</text>}
          </g>
        )
      })}
    </svg>
  )
}

export function InsightsPage() {
  const { data, error, loading } = useLoad<Insights>('/api/insights')
  if (!data) return <main className="page">{loading ? <Spinner /> : <ErrorNote>{error}</ErrorNote>}</main>
  const totalMinutes = data.study_minutes.reduce((s, r) => s + r.minutes, 0)
  const studyDays = data.study_minutes.filter((r) => r.minutes > 0).length
  const busiest = [...data.workload].sort((a, b) => b.minutes - a.minutes)[0]

  return (
    <main className="page wide">
      <PageHead kicker="Insights · from your recorded activity only" title="How it's going" />

      {data.actions.length > 0 && (
        <section className="stack" style={{ marginBottom: 26 }}>
          {data.actions.map((a) => (
            <div key={a.text} className="insight-action">
              <span>{a.text}</span>
              <Link className="btn small primary" to={a.to}>{a.label}</Link>
            </div>
          ))}
        </section>
      )}

      <div className="grid-2">
        <section className="panel">
          <div className="panel-head"><h3>Focused study, last 14 days</h3><span className="mono small">{minutesLabel(totalMinutes)}</span></div>
          {totalMinutes ? (
            <Bars
              rows={data.study_minutes.map((r) => ({ label: weekday.format(new Date(`${r.date}T12:00`)), value: r.minutes, title: shortDate(`${r.date}T12:00`) }))}
              tone="study"
              unit={(v) => minutesLabel(v)}
            />
          ) : <Empty title="No sessions recorded">Use the Study Desk and your focus time appears here.</Empty>}
          <p className="muted small">{studyDays} of 14 days with a focus session.</p>
        </section>

        <section className="panel">
          <div className="panel-head"><h3>Work due, next 14 days</h3><Link className="btn ghost small" to="/planner">Planner</Link></div>
          <Bars
            rows={data.workload.map((r) => ({ label: weekday.format(new Date(`${r.date}T12:00`)), value: r.minutes, title: `${shortDate(`${r.date}T12:00`)} · ${r.items} due${r.exams ? ` · ${r.exams} exam` : ''}`, tone: r.exams ? 'accent' : undefined }))}
            unit={(v) => minutesLabel(v)}
          />
          <p className="muted small">
            Estimated effort of what's due each day; exam days in orange.
            {busiest && busiest.minutes > 0 && ` Heaviest: ${shortDate(`${busiest.date}T12:00`)} with ${minutesLabel(busiest.minutes)}.`}
          </p>
        </section>

        <section className="panel">
          <div className="panel-head"><h3>Syllabus coverage</h3></div>
          {data.coverage.length === 0 ? <Empty title="No syllabus yet">Add one to a subject to track coverage.</Empty> : (
            <div className="stack">
              {data.coverage.map((c) => (
                <div key={c.course.id}>
                  <div className="spread small"><Link to={`/subjects/${c.course.id}`}>{c.course.name}</Link><span className="mono muted">{c.revised + c.practised}/{c.total}</span></div>
                  <div style={{ marginTop: 4 }}><CoverageBar coverage={{ practised: c.practised, revised: c.revised, in_progress: c.in_progress }} total={c.total} /></div>
                </div>
              ))}
              <div className="legend">
                <span><i style={{ background: 'var(--ok)' }} /> Practised</span>
                <span><i style={{ background: 'var(--study)' }} /> Revised</span>
                <span><i style={{ background: 'var(--warn)' }} /> Started</span>
              </div>
            </div>
          )}
        </section>

        <section className="panel">
          <div className="panel-head"><h3>Answers by topic, last 30 days</h3><Link className="btn ghost small" to="/revision?tab=weak">Weak topics</Link></div>
          {data.topic_accuracy.length === 0 ? <Empty title="No answers yet">Practice questions, flashcards and tutor checks are counted here.</Empty> : (
            <div className="stack tight">
              {data.topic_accuracy.map((t) => (
                <div key={t.topic_id} title={`${t.correct} of ${t.attempts} correct`}>
                  <div className="spread small"><Link to={`/topics/${t.topic_id}`} className="clip">{t.title}</Link><span className="mono">{t.correct}/{t.attempts}</span></div>
                  <span className="meter" style={{ marginTop: 3 }}><span className={`fill ${t.rate < 0.6 ? 'accent' : 'ok'}`} style={{ width: `${Math.round(t.rate * 100)}%` }} /></span>
                </div>
              ))}
            </div>
          )}
        </section>
      </div>

      <section className="panel" style={{ marginTop: 16 }}>
        <h3>Finished on time, last 30 days</h3>
        <p style={{ marginTop: 6 }}>
          {data.on_time.rate === null
            ? 'Nothing with a deadline finished in the last 30 days.'
            : `${data.on_time.on_time} of ${data.on_time.done} finished before the deadline (${Math.round(data.on_time.rate * 100)}%).`}
          {' '}<span className="muted small">Counts your own “done” mark and real turn-ins.</span>
        </p>
      </section>
    </main>
  )
}
