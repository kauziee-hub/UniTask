import { useState, type FormEvent } from 'react'
import { Plus } from 'lucide-react'
import { Link, useNavigate } from 'react-router-dom'
import { Empty, ErrorNote, PageHead, Sheet, Spinner } from '../../components/ui'
import { api } from '../../lib/api'
import { dueLabel } from '../../lib/format'
import type { Subject } from '../../lib/types'
import { useAction } from '../../lib/useAction'
import { useLoad } from '../../lib/useLoad'

export function CoverageBar({ coverage, total }: { coverage: Record<string, number>; total: number }) {
  if (!total) return <span className="coverage-bar" />
  return (
    <span className="coverage-bar" role="img" aria-label={`${coverage.practised} practised, ${coverage.revised} revised, ${coverage.in_progress} started, of ${total}`}>
      {(['practised', 'revised', 'in_progress'] as const).map((key) => (
        <span key={key} className={key} style={{ width: `${(100 * (coverage[key] ?? 0)) / total}%` }} />
      ))}
    </span>
  )
}

function NewSubject({ onDone }: { onDone: (s: Subject) => void }) {
  const { busy, error, run } = useAction()
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    run(async () => onDone(await api.post<Subject>('/api/subjects', { name: form.get('name'), code: form.get('code') || '', color: form.get('color') })))
  }
  return (
    <form className="form-grid" onSubmit={submit}>
      <ErrorNote>{error}</ErrorNote>
      <label className="field span-2"><span>Subject name</span><input className="input" name="name" required maxLength={160} placeholder="Operating Systems" /></label>
      <label className="field"><span>Code <span className="hint">· optional</span></span><input className="input" name="code" maxLength={30} placeholder="CS302" /></label>
      <label className="field"><span>Colour</span><input className="input" name="color" type="color" defaultValue="#4a5d8f" style={{ padding: 4 }} /></label>
      <button className="btn primary span-2" type="submit" disabled={busy}>{busy ? 'Saving…' : 'Add subject'}</button>
    </form>
  )
}

export function SubjectsPage() {
  const { data, error, loading } = useLoad<Subject[]>('/api/subjects')
  const [adding, setAdding] = useState(false)
  const navigate = useNavigate()
  return (
    <main className="page wide">
      <PageHead kicker="Syllabus intelligence" title="Subjects">
        <button className="btn primary" type="button" onClick={() => setAdding(true)}><Plus size={15} /> Add subject</button>
      </PageHead>
      <p className="muted" style={{ marginTop: -10, marginBottom: 20 }}>
        Each subject's syllabus becomes a map of modules and topics. Coverage only moves when you study, answer questions or mark it yourself.
      </p>
      <ErrorNote>{error}</ErrorNote>
      {loading && !data && <Spinner />}
      {data && data.length === 0 && (
        <Empty title="No subjects yet">Add a subject, or join a class with a code from your teacher. Classes you join appear here too.</Empty>
      )}
      <div className="grid-3">
        {data?.map((s) => (
          <Link key={s.id} to={`/subjects/${s.id}`} className="subject-card" style={{ ['--c' as string]: s.color }}>
            <span className="muted tiny mono">{s.code || (s.source === 'unitask' ? 'Class' : s.source === 'teams' ? 'Teams' : 'Personal')}</span>
            <h3>{s.name}</h3>
            <div style={{ margin: '12px 0 6px' }}><CoverageBar coverage={s.coverage} total={s.topic_count} /></div>
            <p className="muted small">
              {s.topic_count ? `${s.coverage.revised + s.coverage.practised} of ${s.topic_count} topics revised` : 'No syllabus yet'}
              {s.unconfirmed > 0 && ` · ${s.unconfirmed} to check`}
            </p>
            <p className="muted tiny" style={{ marginTop: 8 }}>
              {s.materials} file{s.materials === 1 ? '' : 's'} · {s.pyq_count} past questions · {s.open_work} open
              {s.next_exam && <> · <span style={{ color: 'var(--accent)' }}>exam {dueLabel(s.next_exam.starts_at)}</span></>}
            </p>
          </Link>
        ))}
      </div>
      <Sheet open={adding} title="Add a subject" onClose={() => setAdding(false)}>
        <NewSubject onDone={(s) => navigate(`/subjects/${s.id}`)} />
      </Sheet>
    </main>
  )
}
