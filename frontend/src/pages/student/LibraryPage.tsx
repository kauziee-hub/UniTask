import { useEffect, useState, type FormEvent } from 'react'
import { RefreshCw, Search, Trash2, Upload } from 'lucide-react'
import { Link, useSearchParams } from 'react-router-dom'
import { AiBadge, Empty, ErrorNote, PageHead, Spinner, Tabs } from '../../components/ui'
import { api } from '../../lib/api'
import { relative } from '../../lib/format'
import type { AiStatus, Citation, Material, Subject } from '../../lib/types'
import { useAction } from '../../lib/useAction'
import { MATERIAL_KINDS } from '../../lib/study'
import { useLoad } from '../../lib/useLoad'

const KINDS = MATERIAL_KINDS
const STATUS: Record<Material['status'], { label: string; tone: string }> = {
  queued: { label: 'Queued', tone: '' },
  processing: { label: 'Reading…', tone: 'warn' },
  ready: { label: 'Searchable', tone: 'ok' },
  needs_ocr: { label: 'Scanned · needs OCR', tone: 'warn' },
  failed: { label: 'Could not read', tone: 'accent' },
}

export function CitationChip({ c }: { c: Citation }) {
  return (
    <Link className="cite" to={`/library/${c.material_id}?page=${c.page}`} title={c.excerpt}>
      {c.label && <b>{c.label}</b>} {c.title} · p.{c.page}
    </Link>
  )
}

export function UploadMaterial({ courseId, onUploaded }: { courseId?: number; onUploaded: () => void }) {
  const { data: subjects } = useLoad<Subject[]>(courseId ? null : '/api/subjects')
  const [kind, setKind] = useState('notes')
  const { busy, error, run } = useAction()
  const [message, setMessage] = useState<string | null>(null)

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    const files = form.getAll('file').filter((f): f is File => f instanceof File && f.size > 0)
    if (!files.length) return
    const target = event.currentTarget
    run(async () => {
      const done: string[] = []
      for (const file of files) {
        const body = new FormData()
        body.append('file', file)
        body.append('kind', kind)
        const course = courseId ?? form.get('course_id')
        if (course) body.append('course_id', String(course))
        if (form.get('year')) body.append('year', String(form.get('year')))
        const material = await api.post<Material>('/api/materials', body)
        done.push(`${material.title}: ${STATUS[material.status].label.toLowerCase()}${material.page_count ? `, ${material.page_count} pages` : ''}`)
      }
      setMessage(done.join(' · '))
      target.reset()
      onUploaded()
    })
  }

  return (
    <form className="panel" onSubmit={submit}>
      <div className="form-grid">
        <label className="dropzone span-2">
          <Upload size={16} />
          <span>PDF, Word, PowerPoint, text or a photo of a page · up to 30 MB each · private to you</span>
          <input name="file" type="file" multiple accept=".pdf,.docx,.pptx,.txt,.md,.png,.jpg,.jpeg,.webp" />
        </label>
        <label className="field">
          <span>What is it?</span>
          <select className="select" value={kind} onChange={(e) => setKind(e.target.value)}>
            {KINDS.map((k) => <option key={k.key} value={k.key}>{k.label}</option>)}
          </select>
        </label>
        {!courseId && (
          <label className="field">
            <span>Subject</span>
            <select className="select" name="course_id" defaultValue="">
              <option value="">No subject</option>
              {subjects?.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
          </label>
        )}
        {kind === 'pyq' && (
          <label className="field">
            <span>Year of the paper</span>
            <input className="input" name="year" type="number" min={1990} max={2100} placeholder="2025" />
          </label>
        )}
        <button className="btn primary span-2" type="submit" disabled={busy}>{busy ? 'Uploading and reading…' : 'Upload'}</button>
      </div>
      <ErrorNote>{error}</ErrorNote>
      {message && <div className="note ok" style={{ marginTop: 10 }}>{message}</div>}
    </form>
  )
}

export function MaterialList({ materials, onChanged }: { materials: Material[]; onChanged: () => void }) {
  const { error, run } = useAction()
  if (!materials.length) return <Empty title="No files yet">Upload lecture notes, slides, a syllabus or past papers. They stay private to your account.</Empty>
  return (
    <div>
      <ErrorNote>{error}</ErrorNote>
      {materials.map((m) => (
        <div key={m.id} className="material-row">
          <span className="icon">{m.filename.split('.').pop()}</span>
          <div style={{ minWidth: 0 }}>
            <Link to={`/library/${m.id}`} className="clip" style={{ display: 'block' }}>{m.title}</Link>
            <span className="muted tiny">
              {KINDS.find((k) => k.key === m.kind)?.label}
              {m.year && ` ${m.year}`}
              {m.course && ` · ${m.course.name}`}
              {m.page_count ? ` · ${m.page_count} pages` : ''} · {relative(m.created_at)}
              {m.extractor && m.extractor !== 'none' && ` · read with ${m.extractor}`}
            </span>
            {m.error && <span className="tiny" style={{ display: 'block', color: 'var(--accent)' }}>{m.error}</span>}
          </div>
          <div className="row" style={{ gap: 6 }}>
            <span className={`pill ${STATUS[m.status].tone}`}>{STATUS[m.status].label}</span>
            {m.status !== 'ready' && (
              <button className="btn ghost icon small" type="button" aria-label="Read again" onClick={() => run(async () => { await api.post(`/api/materials/${m.id}/reprocess`); onChanged() })}>
                <RefreshCw size={13} />
              </button>
            )}
            <button className="btn ghost icon small" type="button" aria-label={`Delete ${m.title}`} onClick={() => run(async () => {
              if (!window.confirm(`Delete ${m.title}? The file is removed from storage.`)) return
              await api.del(`/api/materials/${m.id}`)
              onChanged()
            })}>
              <Trash2 size={13} />
            </button>
          </div>
        </div>
      ))}
    </div>
  )
}

function Ask({ subjects }: { subjects: Subject[] }) {
  const [params] = useSearchParams()
  const [question, setQuestion] = useState(() => params.get('q') ?? '')
  const [course, setCourse] = useState('')
  const [answer, setAnswer] = useState<{ answer: string; citations: Citation[]; conversation_id: number } | null>(null)
  const { busy, error, run } = useAction()
  const { data: ai } = useLoad<AiStatus>('/api/ai/status')
  const submit = (event: FormEvent) => {
    event.preventDefault()
    run(async () => setAnswer(await api.post('/api/ask', { question, course_id: course ? Number(course) : null })))
  }
  return (
    <div className="stack">
      <form className="panel stack" onSubmit={submit}>
        <div className="spread"><h3>Ask your materials</h3><AiBadge ai={ai} /></div>
        <p className="muted small">Answers come only from your own uploaded files, with the page each point came from. If your files don't cover it, you'll be told.</p>
        <textarea className="textarea" rows={3} value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="What are the conditions for a grammar to be LL(1)?" required minLength={2} />
        <div className="row" style={{ gap: 8 }}>
          <select className="select" value={course} onChange={(e) => setCourse(e.target.value)} style={{ maxWidth: 260 }}>
            <option value="">All subjects</option>
            {subjects.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
          <button className="btn primary" type="submit" disabled={busy || question.trim().length < 2}>{busy ? 'Reading your notes…' : 'Ask'}</button>
        </div>
      </form>
      <ErrorNote>{error}</ErrorNote>
      {answer && (
        <div className="panel">
          <p style={{ whiteSpace: 'pre-wrap', lineHeight: 1.65 }}>{answer.answer}</p>
          {answer.citations.length > 0 && <div className="row" style={{ gap: 6, flexWrap: 'wrap', marginTop: 12 }}>{answer.citations.map((c, i) => <CitationChip key={i} c={c} />)}</div>}
          <Link className="btn small" style={{ marginTop: 12 }} to={`/tutor?conversation=${answer.conversation_id}`}>Continue with the tutor →</Link>
        </div>
      )}
    </div>
  )
}

function SearchBox({ subjects }: { subjects: Subject[] }) {
  const [params, setParams] = useSearchParams()
  const q = params.get('q') ?? ''
  const [text, setText] = useState(q)
  const [course, setCourse] = useState('')
  const { data, loading, error } = useLoad<{ hits: Citation[] }>(q.length >= 2 ? `/api/search?q=${encodeURIComponent(q)}${course ? `&course_id=${course}` : ''}` : null)
  return (
    <div className="stack">
      <form className="row" style={{ gap: 8 }} onSubmit={(e) => { e.preventDefault(); setParams({ tab: 'search', q: text }) }}>
        <input className="input" value={text} onChange={(e) => setText(e.target.value)} placeholder="Search inside every page: “subset construction”, “normal forms”…" style={{ flex: 1 }} />
        <select className="select" value={course} onChange={(e) => setCourse(e.target.value)} style={{ maxWidth: 200 }}>
          <option value="">All subjects</option>
          {subjects.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
        </select>
        <button className="btn primary" type="submit"><Search size={14} /> Search</button>
      </form>
      <ErrorNote>{error}</ErrorNote>
      {loading && <Spinner />}
      {data && (data.hits.length === 0 ? <Empty title="No matches">Nothing in your files mentions that. Try a different word.</Empty> : (
        <div>
          {data.hits.map((hit, i) => (
            <div key={i} className="hit">
              <Link to={`/library/${hit.material_id}?page=${hit.page}`} style={{ fontWeight: 500 }}>{hit.title} · page {hit.page}</Link>
              <p className="muted small" style={{ marginTop: 4 }}>{hit.excerpt}</p>
            </div>
          ))}
        </div>
      ))}
    </div>
  )
}

export function LibraryPage() {
  const [params, setParams] = useSearchParams()
  const tab = (params.get('tab') as 'files' | 'search' | 'ask') ?? 'files'
  const { data, error, reload } = useLoad<Material[]>('/api/materials')
  const { data: subjects } = useLoad<Subject[]>('/api/subjects')
  const processing = data?.some((m) => m.status === 'queued' || m.status === 'processing')
  useEffect(() => {
    if (!processing) return
    const timer = window.setInterval(() => void reload(), 2500)
    return () => window.clearInterval(timer)
  }, [processing, reload])

  return (
    <main className="page wide">
      <PageHead kicker="Knowledge library" title="Your materials" />
      <Tabs value={tab} onChange={(t) => setParams({ tab: t })} tabs={[{ key: 'files', label: `Files (${data?.length ?? 0})` }, { key: 'search', label: 'Search' }, { key: 'ask', label: 'Ask' }]} />
      <ErrorNote>{error}</ErrorNote>
      {tab === 'files' && (
        <div className="split">
          <div>{data ? <MaterialList materials={data} onChanged={reload} /> : <Spinner />}</div>
          <UploadMaterial onUploaded={reload} />
        </div>
      )}
      {tab === 'search' && <SearchBox subjects={subjects ?? []} />}
      {tab === 'ask' && <Ask subjects={subjects ?? []} />}
    </main>
  )
}
