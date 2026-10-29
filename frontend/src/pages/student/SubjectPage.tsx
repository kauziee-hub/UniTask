import { useState, type FormEvent } from 'react'
import { Check, Plus, Sparkles, Trash2, X } from 'lucide-react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { Empty, ErrorNote, Spinner, Tabs } from '../../components/ui'
import { api } from '../../lib/api'
import { dueLabel } from '../../lib/format'
import type { ExamSummary, Material, PyqAnalysis, Subject, Syllabus, TopicNode, TopicStatus } from '../../lib/types'
import { useAction } from '../../lib/useAction'
import { STATUSES } from '../../lib/study'
import { useLoad } from '../../lib/useLoad'
import { CoverageBar } from './SubjectsPage'
import { MaterialList, UploadMaterial } from './LibraryPage'

export function StatusPick({ topic, onChange }: { topic: { id: number; status: TopicStatus }; onChange: (status: TopicStatus) => void }) {
  return (
    <span className="status-pick" role="group" aria-label="Coverage">
      {STATUSES.map((s) => (
        <button key={s.key} type="button" className={`s-${s.key}`} aria-pressed={topic.status === s.key} title={s.label} onClick={() => onChange(s.key)}>
          {s.short}
        </button>
      ))}
    </span>
  )
}

function TopicRow({ topic, onStatus, onDelete }: { topic: TopicNode; onStatus: (t: TopicNode, s: TopicStatus) => void; onDelete: (t: TopicNode) => void }) {
  return (
    <div className={`topic-row${topic.confirmed ? '' : ' unconfirmed'}`}>
      <StatusPick topic={topic} onChange={(s) => onStatus(topic, s)} />
      <div style={{ minWidth: 0 }}>
        <Link to={`/topics/${topic.id}`}>{topic.title}</Link>
        <div className="meta">
          {topic.material_pages > 0 ? <span>{topic.material_pages} page{topic.material_pages > 1 ? 's' : ''} in your notes</span> : <span style={{ color: 'var(--warn)' }}>no material yet</span>}
          {topic.pyq_count > 0 && <span>asked {topic.pyq_count}× in past papers</span>}
          {topic.weak_reason && <span style={{ color: 'var(--accent)' }}>weak: {topic.weak_reason}</span>}
          {topic.prerequisites.length > 0 && <span>needs {topic.prerequisites.map((p) => p.title + (p.suggested ? ' (suggested)' : '')).join(', ')}</span>}
          {!topic.confirmed && <span>extracted · check it</span>}
        </div>
      </div>
      <button className="btn ghost icon small" type="button" aria-label={`Remove ${topic.title}`} onClick={() => onDelete(topic)}><X size={13} /></button>
    </div>
  )
}

function SyllabusTab({ course, subject }: { course: number; subject: Subject }) {
  const { data, setData, error, loading } = useLoad<Syllabus>(`/api/subjects/${course}/syllabus`)
  const action = useAction()
  const [text, setText] = useState('')
  const [materialId, setMaterialId] = useState('')
  const { data: materials } = useLoad<Material[]>(`/api/materials?course_id=${course}`)

  const status = (topic: TopicNode, value: TopicStatus) =>
    action.run(async () => {
      await api.patch(`/api/topics/${topic.id}`, { status: value })
      setData(await api.get<Syllabus>(`/api/subjects/${course}/syllabus`))
    })
  const remove = (topic: TopicNode) =>
    action.run(async () => {
      if (!window.confirm(`Remove “${topic.title}”${topic.parent_id ? '' : ' and its topics'}?`)) return
      await api.del(`/api/topics/${topic.id}`)
      setData(await api.get<Syllabus>(`/api/subjects/${course}/syllabus`))
    })
  const extract = () =>
    action.run(async () => {
      const result = await api.post<{ syllabus: Syllabus; method: string; created: number }>(`/api/subjects/${course}/syllabus/extract`, materialId ? { material_id: Number(materialId) } : { text })
      setData(result.syllabus)
      setText('')
    })
  const confirm = (accept: boolean) => action.run(async () => setData(await api.post<Syllabus>(`/api/subjects/${course}/syllabus/confirm`, { accept })))
  const suggest = () => action.run(async () => setData((await api.post<{ syllabus: Syllabus }>(`/api/subjects/${course}/suggest-links`)).syllabus))
  const addTopic = (event: FormEvent<HTMLFormElement>, parent: number | null) => {
    event.preventDefault()
    const form = event.currentTarget
    const title = new FormData(form).get('title')
    action.run(async () => {
      await api.post(`/api/subjects/${course}/topics`, { title, parent_id: parent })
      form.reset()
      setData(await api.get<Syllabus>(`/api/subjects/${course}/syllabus`))
    })
  }

  if (!data) return loading ? <Spinner /> : <ErrorNote>{error}</ErrorNote>
  const syllabusFiles = (materials ?? []).filter((m) => m.status === 'ready')
  return (
    <div className="stack" style={{ gap: 18 }}>
      <ErrorNote>{action.error}</ErrorNote>
      {data.topic_count > 0 && (
        <div className="panel">
          <div className="spread"><h3>Coverage</h3><span className="muted small mono">{data.coverage.revised + data.coverage.practised}/{data.topic_count} revised or practised</span></div>
          <div style={{ margin: '10px 0' }}><CoverageBar coverage={data.coverage} total={data.topic_count} /></div>
          <div className="legend">
            <span><i style={{ background: 'var(--ok)' }} /> Practised {data.coverage.practised}</span>
            <span><i style={{ background: 'var(--study)' }} /> Revised {data.coverage.revised}</span>
            <span><i style={{ background: 'var(--warn)' }} /> Started {data.coverage.in_progress}</span>
            <span><i style={{ background: 'var(--sunken)', border: '1px solid var(--rule)' }} /> Not started {data.coverage.not_started}</span>
          </div>
          {data.without_material.length > 0 && (
            <p className="small" style={{ marginTop: 10, color: 'var(--warn)' }}>
              No notes found for: {data.without_material.slice(0, 6).join(', ')}{data.without_material.length > 6 && ` and ${data.without_material.length - 6} more`}. <Link to="/library">Upload material</Link>
            </p>
          )}
        </div>
      )}

      {data.unconfirmed > 0 && (
        <div className="note" style={{ alignItems: 'center', flexWrap: 'wrap', background: 'var(--warn-soft)' }}>
          <span style={{ flex: 1 }}>{data.unconfirmed} modules and topics were read from your syllabus. Check them (highlighted), remove anything wrong, then confirm.</span>
          <button className="btn small primary" type="button" onClick={() => confirm(true)}><Check size={13} /> Confirm all</button>
          <button className="btn small" type="button" onClick={() => confirm(false)}>Discard extracted</button>
        </div>
      )}

      {data.modules.length === 0 && (
        <div className="panel">
          <h3>Add the syllabus</h3>
          <p className="muted small" style={{ margin: '4px 0 12px' }}>
            Paste it, or choose an uploaded syllabus file. Lines like “Module 1: Title” followed by topics are read directly; anything else is structured by the AI and shown to you to check.
          </p>
          {syllabusFiles.length > 0 && (
            <label className="field" style={{ marginBottom: 10 }}>
              <span>From a file in your library</span>
              <select className="select" value={materialId} onChange={(e) => setMaterialId(e.target.value)}>
                <option value="">— paste text instead —</option>
                {syllabusFiles.map((m) => <option key={m.id} value={m.id}>{m.title}</option>)}
              </select>
            </label>
          )}
          {!materialId && (
            <textarea className="textarea" rows={8} value={text} onChange={(e) => setText(e.target.value)} placeholder={'Module 1: Lexical Analysis\nTokens, lexemes, patterns; Regular expressions; Finite automata\nModule 2: Syntax Analysis\n…'} />
          )}
          <button className="btn primary" type="button" style={{ marginTop: 10 }} onClick={extract} disabled={action.busy || (!materialId && text.trim().length < 20)}>
            {action.busy ? 'Reading…' : 'Build the syllabus map'}
          </button>
        </div>
      )}

      {data.modules.map((module) => (
        <section key={module.id} className="module">
          <div className="module-head">
            <h3>{module.title}</h3>
            {!module.confirmed && <span className="pill warn">extracted</span>}
            <button className="btn ghost icon small" type="button" aria-label={`Remove module ${module.title}`} onClick={() => remove(module)}><Trash2 size={13} /></button>
          </div>
          {(module.topics ?? []).map((t) => <TopicRow key={t.id} topic={t} onStatus={status} onDelete={remove} />)}
          {(module.topics ?? []).length === 0 && <TopicRow topic={module} onStatus={status} onDelete={remove} />}
          <form className="topic-row" onSubmit={(e) => addTopic(e, module.id)} style={{ gridTemplateColumns: 'minmax(0,1fr) auto' }}>
            <input className="input" name="title" placeholder="Add a topic to this module" required maxLength={300} style={{ height: 30 }} />
            <button className="btn small" type="submit"><Plus size={13} /> Add</button>
          </form>
        </section>
      ))}

      {data.modules.length > 0 && (
        <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
          <form onSubmit={(e) => addTopic(e, null)} className="row" style={{ gap: 8 }}>
            <input className="input" name="title" placeholder="New module" required maxLength={300} style={{ width: 220 }} />
            <button className="btn small" type="submit"><Plus size={13} /> Module</button>
          </form>
          <button className="btn small" type="button" onClick={suggest} disabled={action.busy}><Sparkles size={13} /> Suggest prerequisites</button>
          {subject.editable && <span className="muted tiny">Suggested links stay marked until you accept them on the topic page.</span>}
        </div>
      )}
    </div>
  )
}

function PastPapersTab({ course }: { course: number }) {
  const { data, loading, error } = useLoad<PyqAnalysis>(`/api/subjects/${course}/pyq`)
  if (!data) return loading ? <Spinner /> : <ErrorNote>{error}</ErrorNote>
  return (
    <div className="stack" style={{ gap: 18 }}>
      <div className="note">{data.note}</div>
      {data.papers.length === 0 ? (
        <Empty title="No past papers yet">Upload previous-year papers in the Library with the type “Past paper” and the year. Questions are read, matched to topics and grouped when they repeat.</Empty>
      ) : (
        <>
          <p className="muted small">{data.total_questions} questions from {data.papers.length} paper{data.papers.length > 1 ? 's' : ''}: {data.papers.map((p) => p.year ?? p.title).join(', ')}.</p>
          <div className="grid-2">
            <section className="panel">
              <h3>Asked most often</h3>
              <div className="stack" style={{ marginTop: 10 }}>
                {data.groups.filter((g) => g.count > 1).slice(0, 8).map((g) => (
                  <div key={g.pattern_key}>
                    <div className="spread"><span className="pill accent">{g.count}× · {g.years.join(', ')}</span>{g.topic_id && <Link className="small" to={`/topics/${g.topic_id}`}>{g.topic}</Link>}</div>
                    <p className="small" style={{ marginTop: 4 }}>{g.questions[0].text}</p>
                  </div>
                ))}
                {data.groups.every((g) => g.count < 2) && <p className="muted small">No question has repeated yet across your papers.</p>}
              </div>
            </section>
            <section className="panel">
              <h3>Questions per topic</h3>
              <div className="stack tight" style={{ marginTop: 10 }}>
                {data.by_topic.map((row) => (
                  <div key={row.topic} className="spread small">
                    {row.topic_id ? <Link to={`/topics/${row.topic_id}`}>{row.topic}</Link> : <span className="muted">{row.topic}</span>}
                    <span className="mono">{row.count}</span>
                  </div>
                ))}
              </div>
            </section>
          </div>
          <section>
            <div className="section-head"><h2>Every question</h2></div>
            {data.groups.map((g) => g.questions.map((q) => (
              <div key={q.id} className="hit">
                <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
                  <span className="mono tiny">{q.year ?? '—'} {q.label}</span>
                  {q.marks && <span className="pill">{q.marks} marks</span>}
                  {g.count > 1 && <span className="pill accent">repeats</span>}
                  {g.topic && <span className="muted tiny">{g.topic}</span>}
                </div>
                <p style={{ marginTop: 4 }}>{q.text}</p>
                {g.topic_id ? <Link className="small" to={`/topics/${g.topic_id}?practice=${q.id}`}>Practise this →</Link> : <Link className="small" to={`/revision?tab=test&course=${course}`}>Practise in a test →</Link>}
              </div>
            )))}
          </section>
        </>
      )}
    </div>
  )
}

export function SubjectPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const course = Number(id)
  const [tab, setTab] = useState<'syllabus' | 'materials' | 'papers' | 'exams'>('syllabus')
  const { data: subjects } = useLoad<Subject[]>('/api/subjects')
  const { data: materials, reload: reloadMaterials } = useLoad<Material[]>(`/api/materials?course_id=${course}`)
  const { data: exams } = useLoad<ExamSummary[]>('/api/exams')
  const subject = subjects?.find((s) => s.id === course)

  if (!subjects) return <main className="page"><Spinner /></main>
  if (!subject) return <main className="page"><ErrorNote>Subject not found.</ErrorNote></main>

  const remove = async () => {
    if (!window.confirm(`Delete ${subject.name} with its syllabus, files and exams?`)) return
    await api.del(`/api/subjects/${subject.id}`)
    navigate('/subjects')
  }

  return (
    <main className="page wide">
      <nav className="crumbs"><Link to="/subjects">Subjects</Link></nav>
      <header className="page-head">
        <div>
          <p className="kicker" style={{ color: subject.color }}>{subject.code || (subject.source === 'unitask' ? `Class · ${subject.my_role}` : 'Personal subject')}</p>
          <h1 className="title page-title">{subject.name}</h1>
        </div>
        <div className="row page-actions">
          <Link className="btn" to={`/tutor?course=${subject.id}`}>Ask the tutor</Link>
          {subject.next_exam && <Link className="btn accent" to={`/exams/${subject.next_exam.id}`}>Exam {dueLabel(subject.next_exam.starts_at)}</Link>}
          {subject.editable && subject.source === 'personal' && <button className="btn ghost danger" type="button" onClick={remove}><Trash2 size={14} /></button>}
        </div>
      </header>
      <Tabs
        value={tab}
        onChange={setTab}
        tabs={[
          { key: 'syllabus', label: 'Syllabus map', count: subject.unconfirmed },
          { key: 'materials', label: `Materials (${subject.materials})` },
          { key: 'papers', label: `Past papers (${subject.pyq_count})` },
          { key: 'exams', label: 'Exams' },
        ]}
      />
      {tab === 'syllabus' && <SyllabusTab course={course} subject={subject} />}
      {tab === 'materials' && (
        <div className="stack">
          <UploadMaterial courseId={course} onUploaded={reloadMaterials} />
          <MaterialList materials={materials ?? []} onChanged={reloadMaterials} />
        </div>
      )}
      {tab === 'papers' && <PastPapersTab course={course} />}
      {tab === 'exams' && (
        <div className="stack">
          {(exams ?? []).filter((e) => e.course?.id === course).map((e) => (
            <Link key={e.id} className="panel" to={`/exams/${e.id}`} style={{ textDecoration: 'none' }}>
              <div className="spread"><strong>{e.title}</strong><span className="mono small">{dueLabel(e.starts_at)}</span></div>
              <span className="muted small">{e.covered_count}/{e.topic_count} topics revised · {e.planned_blocks} study blocks planned</span>
            </Link>
          ))}
          <Link className="btn" to={`/exams?new=${course}`}><Plus size={14} /> Add an exam for this subject</Link>
        </div>
      )}
    </main>
  )
}
