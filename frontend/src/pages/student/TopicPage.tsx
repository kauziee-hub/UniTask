import { useState } from 'react'
import { BrainCircuit, Check, Play, Sparkles, X } from 'lucide-react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { ErrorNote, Spinner } from '../../components/ui'
import { api } from '../../lib/api'
import { dueLabel, minutesLabel, relative } from '../../lib/format'
import type { Citation, PastQuestion, TopicDetail } from '../../lib/types'
import { useAction } from '../../lib/useAction'
import { useLoad } from '../../lib/useLoad'
import { CitationChip } from './LibraryPage'
import { StatusPick } from './SubjectPage'
import { startSession } from '../../lib/study'

export function Confidence({ value, onChange }: { value: number | null; onChange: (n: number) => void }) {
  return (
    <span className="confidence" role="group" aria-label="How sure are you? 1 to 5">
      {[1, 2, 3, 4, 5].map((n) => (
        <button key={n} type="button" aria-pressed={value === n} onClick={() => onChange(n)}>{n}</button>
      ))}
    </span>
  )
}

export function Practice({ question, onDone }: { question: PastQuestion; onDone?: () => void }) {
  const [answer, setAnswer] = useState('')
  const [confidence, setConfidence] = useState<number | null>(null)
  const [result, setResult] = useState<{ graded: boolean; correct?: boolean; feedback?: string | null; citations?: Citation[]; card_created?: boolean; message?: string } | null>(null)
  const { busy, error, run } = useAction()
  const submit = (selfCorrect?: boolean) =>
    run(async () => {
      const r = await api.post<NonNullable<typeof result>>(`/api/questions/${question.id}/practice`, { answer, confidence, self_correct: selfCorrect ?? null })
      setResult(r)
      if (r.graded) onDone?.()
    })
  return (
    <div className="panel stack">
      <div className="row" style={{ gap: 8 }}>
        <span className="mono tiny">{question.year ?? ''} {question.label}</span>
        {question.marks && <span className="pill">{question.marks} marks</span>}
      </div>
      <p style={{ fontWeight: 500 }}>{question.text}</p>
      <textarea className="textarea" rows={5} value={answer} onChange={(e) => setAnswer(e.target.value)} placeholder="Write your answer as you would in the exam." disabled={Boolean(result?.graded)} />
      <div className="row" style={{ gap: 10, flexWrap: 'wrap' }}>
        <span className="small muted">How sure are you?</span>
        <Confidence value={confidence} onChange={setConfidence} />
        {!result?.graded && <button className="btn primary" type="button" disabled={busy || !answer.trim()} onClick={() => submit()}>{busy ? 'Grading…' : 'Check my answer'}</button>}
      </div>
      <ErrorNote>{error}</ErrorNote>
      {result && !result.graded && (
        <div className="note" style={{ flexWrap: 'wrap', alignItems: 'center' }}>
          <span style={{ flex: 1 }}>{result.message}</span>
          <button className="btn small" type="button" onClick={() => submit(true)}><Check size={13} /> I got it right</button>
          <button className="btn small" type="button" onClick={() => submit(false)}><X size={13} /> I got it wrong</button>
        </div>
      )}
      {result?.graded && (
        <div className={`note ${result.correct ? 'ok' : 'error'}`} style={{ flexDirection: 'column' }}>
          <strong>{result.correct ? 'Correct' : 'Not quite'}</strong>
          {result.feedback && <span>{result.feedback}</span>}
          {result.card_created && <span className="small">Added to your revision cards so it comes back.</span>}
          {result.citations && result.citations.length > 0 && <div className="row" style={{ gap: 6, flexWrap: 'wrap' }}>{result.citations.map((c, i) => <CitationChip key={i} c={c} />)}</div>}
        </div>
      )}
    </div>
  )
}

export function TopicPage() {
  const { id } = useParams()
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const { data: topic, setData, error, reload } = useLoad<TopicDetail>(`/api/topics/${id}`)
  const action = useAction()
  const [practising, setPractising] = useState<number | null>(params.get('practice') ? Number(params.get('practice')) : null)

  if (!topic) return <main className="page">{error ? <ErrorNote>{error}</ErrorNote> : <Spinner />}</main>

  const setStatus = (status: TopicDetail['status']) =>
    action.run(async () => {
      await api.patch(`/api/topics/${topic.id}`, { status })
      setData({ ...topic, status })
    })
  const study = () =>
    action.run(async () => {
      const session = await startSession({ kind: 'topic', topic_id: topic.id, planned_minutes: 30 })
      navigate(`/study/${session.id}`)
    })
  const cards = () =>
    action.run(async () => {
      const result = await api.post<{ created: number }>(`/api/topics/${topic.id}/cards/generate`)
      await reload()
      window.alert(`${result.created} flashcards made from your pages. They're in Revision.`)
    })
  const accept = (linkId: number) => action.run(async () => { await api.post(`/api/topic-links/${linkId}/accept`); await reload() })
  const unlink = (linkId: number) => action.run(async () => { await api.del(`/api/topic-links/${linkId}`); await reload() })
  const accuracy = topic.evidence.attempts ? `${topic.evidence.correct}/${topic.evidence.attempts} correct` : 'no answers yet'

  return (
    <main className="page wide">
      <nav className="crumbs">
        <Link to="/subjects">Subjects</Link>
        {topic.course && <><span>/</span><Link to={`/subjects/${topic.course.id}`}>{topic.course.name}</Link></>}
        {topic.module && <><span>/</span><span>{topic.module}</span></>}
      </nav>
      <header className="page-head">
        <div>
          <p className="kicker">Topic</p>
          <h1 className="title page-title">{topic.title}</h1>
        </div>
        <div className="row page-actions">
          <StatusPick topic={topic} onChange={setStatus} />
          <button className="btn primary" type="button" onClick={study} disabled={action.busy}><Play size={14} /> Study now</button>
          <Link className="btn" to={`/tutor?topic=${topic.id}`}><BrainCircuit size={14} /> Learn with the tutor</Link>
        </div>
      </header>
      <ErrorNote>{action.error}</ErrorNote>
      {topic.evidence.weak_reason && <div className="note error" style={{ marginBottom: 16 }}>Weak spot: {topic.evidence.weak_reason}. Practise it below or with the tutor.</div>}

      <dl className="facts" style={{ marginTop: 0 }}>
        <div><dt>Your answers</dt><dd className="mono">{accuracy}</dd></div>
        <div><dt>Studied</dt><dd className="mono">{minutesLabel(topic.studied_minutes)}</dd></div>
        <div><dt>Flashcards</dt><dd className="mono">{topic.cards}</dd></div>
        <div><dt>In past papers</dt><dd className="mono">{topic.questions.length}×</dd></div>
        {topic.exams[0] && <div><dt>Next exam</dt><dd className="mono"><Link to={`/exams/${topic.exams[0].id}`}>{dueLabel(topic.exams[0].starts_at)}</Link></dd></div>}
      </dl>

      <div className="split" style={{ marginTop: 24 }}>
        <div className="stack" style={{ gap: 22 }}>
          <section>
            <div className="section-head" style={{ marginTop: 0 }}><h2>Where your notes cover it</h2></div>
            {topic.pages.length === 0 ? (
              <p className="muted">None of your files mention this topic yet. <Link to="/library">Upload notes</Link> for it.</p>
            ) : (
              topic.pages.map((p, i) => (
                <div key={i} className="hit">
                  <Link to={`/library/${p.material_id}?page=${p.page}`} style={{ fontWeight: 500 }}>{p.title} · page {p.page}</Link>
                  <p className="muted small" style={{ marginTop: 4 }}>{p.excerpt}</p>
                </div>
              ))
            )}
          </section>

          <section>
            <div className="section-head"><h2>Past-paper questions</h2><span className="aside">history, not prediction</span></div>
            {topic.questions.length === 0 && <p className="muted">No past-paper question has been matched to this topic.</p>}
            {topic.questions.map((q) => (
              practising === q.id ? <Practice key={q.id} question={q} onDone={() => void reload()} /> : (
                <div key={q.id} className="hit">
                  <div className="row" style={{ gap: 8 }}><span className="mono tiny">{q.year} {q.label}</span>{q.marks && <span className="pill">{q.marks} marks</span>}</div>
                  <p style={{ marginTop: 4 }}>{q.text}</p>
                  <button className="btn small" type="button" style={{ marginTop: 6 }} onClick={() => setPractising(q.id)}>Answer it</button>
                </div>
              )
            ))}
          </section>
        </div>

        <aside className="stack">
          <div className="panel">
            <h3>Flashcards</h3>
            <p className="muted small" style={{ margin: '4px 0 10px' }}>Written only from your own pages on this topic, each linked to its page.</p>
            <button className="btn small" type="button" onClick={cards} disabled={action.busy || topic.pages.length === 0}><Sparkles size={13} /> Make flashcards</button>
          </div>
          <div className="panel">
            <h3>Builds on</h3>
            {topic.prerequisites.length === 0 && <p className="muted small">No prerequisites recorded.</p>}
            {topic.prerequisites.map((p) => (
              <div key={p.link_id} className="spread small" style={{ marginTop: 6 }}>
                <Link to={`/topics/${p.topic_id}`}>{p.title}</Link>
                <span className="row" style={{ gap: 4 }}>
                  {p.suggested && <><span className="pill warn">suggested</span><button className="btn ghost small" type="button" onClick={() => accept(p.link_id)}>Accept</button></>}
                  <button className="btn ghost icon small" type="button" aria-label="Remove link" onClick={() => unlink(p.link_id)}><X size={12} /></button>
                </span>
              </div>
            ))}
            {topic.dependants.length > 0 && <p className="muted small" style={{ marginTop: 10 }}>Needed for: {topic.dependants.map((d) => d.title).join(', ')}</p>}
          </div>
          <div className="panel">
            <h3>What the tutor has noticed</h3>
            {topic.memory.length === 0 ? <p className="muted small">Nothing yet. Answer the tutor's check questions and it will remember what you got wrong.</p> : (
              <ul className="list small">
                {topic.memory.map((m) => <li key={m.id} style={{ padding: '4px 0' }}><span className="pill">{m.kind}</span> {m.text}</li>)}
              </ul>
            )}
          </div>
          {topic.recent_attempts.length > 0 && (
            <div className="panel">
              <h3>Recent answers</h3>
              {topic.recent_attempts.map((a, i) => (
                <div key={i} className="spread small" style={{ marginTop: 6 }}>
                  <span className="clip">{a.prompt}</span>
                  <span className={`pill ${a.correct ? 'ok' : a.correct === false ? 'accent' : ''}`}>{a.correct ? 'right' : a.correct === false ? 'wrong' : '—'}</span>
                </div>
              ))}
              <p className="muted tiny" style={{ marginTop: 8 }}>Last answered {topic.evidence.last_at ? relative(topic.evidence.last_at) : '—'}</p>
            </div>
          )}
        </aside>
      </div>
    </main>
  )
}
