import { useState, type FormEvent } from 'react'
import { Plus, Trash2 } from 'lucide-react'
import { Link, useSearchParams } from 'react-router-dom'
import { Empty, ErrorNote, PageHead, Spinner, Tabs } from '../../components/ui'
import { api } from '../../lib/api'
import { shortDate } from '../../lib/format'
import type { Card, PastQuestion, PyqAnalysis, Subject, WeakTopic } from '../../lib/types'
import { useAction } from '../../lib/useAction'
import { useLoad } from '../../lib/useLoad'
import { Confidence, Practice } from './TopicPage'

interface RevisionHome {
  due: Card[]
  due_count: number
  total_cards: number
  upcoming: { date: string; count: number }[]
  weak_topics: WeakTopic[]
  history: { date: string; attempts: number; correct: number }[]
}

const GRADES = [
  { key: 'again', label: 'Again', hint: '10 min' },
  { key: 'hard', label: 'Hard', hint: 'sooner' },
  { key: 'good', label: 'Good', hint: 'on schedule' },
  { key: 'easy', label: 'Easy', hint: 'later' },
] as const

function Review({ data, reload }: { data: RevisionHome; reload: () => void }) {
  const [index, setIndex] = useState(0)
  const [shown, setShown] = useState(false)
  const [confidence, setConfidence] = useState<number | null>(null)
  const [reviewed, setReviewed] = useState(0)
  const { busy, error, run } = useAction()
  const card = data.due[index]

  if (!card) {
    return (
      <div className="panel" style={{ textAlign: 'center', padding: 36 }}>
        <p className="title" style={{ fontSize: 28 }}>{reviewed ? `${reviewed} reviewed.` : 'Nothing due right now.'}</p>
        <p className="muted" style={{ marginTop: 6 }}>
          {data.upcoming.length ? `Next: ${data.upcoming[0].count} card${data.upcoming[0].count > 1 ? 's' : ''} on ${shortDate(data.upcoming[0].date)}.` : 'Make cards from a topic, or get some wrong in practice — mistakes come back here.'}
        </p>
        {reviewed > 0 && <button className="btn" type="button" style={{ marginTop: 14 }} onClick={() => { setIndex(0); setReviewed(0); reload() }}>Check for more</button>}
      </div>
    )
  }

  const grade = (g: string) =>
    run(async () => {
      await api.post(`/api/cards/${card.id}/review`, { grade: g, confidence })
      setShown(false)
      setConfidence(null)
      setReviewed((n) => n + 1)
      setIndex((i) => i + 1)
    })

  return (
    <div className="stack" style={{ maxWidth: 680 }}>
      <div className="spread small muted"><span>{index + 1} of {data.due.length} due{card.topic && ` · ${card.topic}`}</span><span>{card.origin === 'mistake' ? 'From a mistake you made' : card.origin === 'ai' ? 'Made from your notes' : 'Your card'}</span></div>
      <div className="flashcard">
        <p className="front">{card.front}</p>
        {shown && (
          <div className="back">
            {card.back}
            {card.material_id && <p className="tiny" style={{ marginTop: 10 }}><Link to={`/library/${card.material_id}?page=${card.page_no}`}>Source: page {card.page_no}</Link></p>}
          </div>
        )}
      </div>
      <ErrorNote>{error}</ErrorNote>
      {!shown ? (
        <div className="row" style={{ gap: 12, flexWrap: 'wrap' }}>
          <span className="small muted">Before you look, how sure are you?</span>
          <Confidence value={confidence} onChange={setConfidence} />
          <button className="btn primary" type="button" onClick={() => setShown(true)}>Show answer</button>
        </div>
      ) : (
        <div className="grades">
          {GRADES.map((g) => (
            <button key={g.key} className={`btn${g.key === 'good' ? ' primary' : ''}`} type="button" disabled={busy} onClick={() => grade(g.key)}>
              {g.label}<small>{g.hint}</small>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

function PracticeTest() {
  const [params, setParams] = useSearchParams()
  const course = params.get('course') ?? ''
  const { data: subjects } = useLoad<Subject[]>('/api/subjects')
  const { data: pyq, loading } = useLoad<PyqAnalysis>(course ? `/api/subjects/${course}/pyq` : null)
  const [seed, setSeed] = useState(0)
  const [index, setIndex] = useState(0)
  const [answered, setAnswered] = useState(0)

  const questions: PastQuestion[] = (pyq?.groups ?? []).map((g) => g.questions[(seed + g.questions.length) % g.questions.length]).slice(0, 5)
  const withPapers = (subjects ?? []).filter((s) => s.pyq_count > 0)
  return (
    <div className="stack" style={{ maxWidth: 760 }}>
      <p className="muted">Five questions from your own past papers, most-repeated first. Each answer is graded against your notes and recorded, so weak topics show up honestly.</p>
      <div className="row" style={{ gap: 8 }}>
        <select className="select" value={course} onChange={(e) => { setParams({ tab: 'test', course: e.target.value }); setIndex(0); setAnswered(0) }} style={{ maxWidth: 320 }}>
          <option value="">Choose a subject</option>
          {withPapers.map((s) => <option key={s.id} value={s.id}>{s.name} · {s.pyq_count} questions</option>)}
        </select>
        {course && <button className="btn" type="button" onClick={() => { setSeed(seed + 1); setIndex(0); setAnswered(0) }}>New set</button>}
      </div>
      {subjects && withPapers.length === 0 && <Empty title="No past papers yet">Upload previous-year papers in the Library (type “Past paper”) to practise from them.</Empty>}
      {loading && <Spinner />}
      {course && pyq && questions.length > 0 && (
        index < questions.length ? (
          <>
            <p className="small mono">Question {index + 1} of {questions.length}</p>
            <Practice key={`${seed}-${questions[index].id}`} question={questions[index]} onDone={() => setAnswered((n) => n + 1)} />
            <div className="row" style={{ gap: 8 }}>
              <button className="btn" type="button" onClick={() => setIndex(index + 1)}>{answered > index ? 'Next question' : 'Skip'}</button>
            </div>
          </>
        ) : (
          <div className="note ok">Test finished: {answered} answered. Results are on each topic and in Insights. <Link to="/insights">See insights</Link></div>
        )
      )}
    </div>
  )
}

function CardsTab() {
  const { data, setData, reload } = useLoad<Card[]>('/api/cards')
  const { data: subjects } = useLoad<Subject[]>('/api/subjects')
  const { busy, error, run } = useAction()
  const add = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const form = event.currentTarget
    const f = new FormData(form)
    run(async () => {
      await api.post('/api/cards', { front: f.get('front'), back: f.get('back'), course_id: f.get('course_id') ? Number(f.get('course_id')) : null })
      form.reset()
      await reload()
    })
  }
  return (
    <div className="split">
      <div>
        {data && data.length === 0 && <Empty title="No cards">Write one, generate them from a topic's pages, or let practice mistakes create them.</Empty>}
        {data?.map((c) => (
          <div key={c.id} className="hit">
            <div className="spread">
              <strong style={{ fontWeight: 500 }}>{c.front}</strong>
              <button className="btn ghost icon small" type="button" aria-label="Delete card" onClick={() => run(async () => { await api.del(`/api/cards/${c.id}`); setData(data.filter((x) => x.id !== c.id)) })}><Trash2 size={13} /></button>
            </div>
            <p className="muted small">{c.back}</p>
            <p className="tiny muted">{c.topic ?? 'No topic'} · {c.origin} · next {shortDate(c.due_at)} · {c.reps} reviews{c.lapses ? `, ${c.lapses} lapses` : ''}</p>
          </div>
        ))}
      </div>
      <form className="panel form-grid" onSubmit={add}>
        <h3 className="span-2">New card</h3>
        <ErrorNote>{error}</ErrorNote>
        <label className="field span-2"><span>Question</span><textarea className="textarea" name="front" rows={2} required maxLength={2000} /></label>
        <label className="field span-2"><span>Answer</span><textarea className="textarea" name="back" rows={3} required maxLength={4000} /></label>
        <label className="field span-2"><span>Subject</span><select className="select" name="course_id" defaultValue=""><option value="">—</option>{subjects?.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</select></label>
        <button className="btn primary span-2" type="submit" disabled={busy}><Plus size={14} /> Add card</button>
      </form>
    </div>
  )
}

export function RevisionPage() {
  const [params, setParams] = useSearchParams()
  const tab = (params.get('tab') as 'review' | 'test' | 'weak' | 'cards') ?? 'review'
  const { data, error, loading, reload } = useLoad<RevisionHome>('/api/revision')
  return (
    <main className="page">
      <PageHead kicker="Revision intelligence" title="Revision" />
      <ErrorNote>{error}</ErrorNote>
      <Tabs
        value={tab}
        onChange={(t) => setParams({ tab: t })}
        tabs={[
          { key: 'review', label: 'Due cards', count: data?.due_count },
          { key: 'test', label: 'Practice test' },
          { key: 'weak', label: 'Weak topics', count: data?.weak_topics.length },
          { key: 'cards', label: `All cards (${data?.total_cards ?? 0})` },
        ]}
      />
      {loading && !data && <Spinner />}
      {tab === 'review' && data && <Review data={data} reload={reload} />}
      {tab === 'test' && <PracticeTest />}
      {tab === 'weak' && data && (
        data.weak_topics.length === 0 ? (
          <Empty title="No weak topics found">Weak topics come only from your answers (at least two) and how sure you said you were. Practise a few questions and this fills in.</Empty>
        ) : (
          <div className="stack">
            {data.weak_topics.map((t) => (
              <div key={t.topic_id} className="panel spread">
                <div>
                  <Link to={`/topics/${t.topic_id}`} style={{ fontWeight: 500 }}>{t.title}</Link>
                  <span className="muted small" style={{ display: 'block' }}>{t.course?.name} · {t.reason}</span>
                </div>
                <div className="row" style={{ gap: 6 }}>
                  <Link className="btn small" to={`/topics/${t.topic_id}`}>Practise</Link>
                  <Link className="btn small primary" to={`/tutor?topic=${t.topic_id}`}>Tutor</Link>
                </div>
              </div>
            ))}
          </div>
        )
      )}
      {tab === 'cards' && <CardsTab />}
    </main>
  )
}
