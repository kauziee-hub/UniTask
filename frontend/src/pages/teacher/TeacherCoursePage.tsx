import { useState, type FormEvent } from 'react'
import { Copy, Paperclip, Plus, RefreshCw, Upload } from 'lucide-react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { Empty, ErrorNote, Sheet, Spinner, Toast } from '../../components/ui'
import { api, type Course, type Member, type TeacherWork } from '../../lib/api'
import { dueLabel, fromLocalInput, relative, shortDate } from '../../lib/format'
import { useLoad } from '../../lib/useLoad'

function defaultDue() {
  const date = new Date()
  date.setDate(date.getDate() + 7)
  date.setHours(23, 59, 0, 0)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T23:59`
}

function NewAssignment({ courseId, onCreated }: { courseId: string; onCreated: () => void }) {
  const [file, setFile] = useState<File | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    const due = fromLocalInput(String(form.get('due_local') ?? ''))
    form.delete('due_local')
    if (due) form.set('due_at', due)
    if (!form.get('points')) form.delete('points')
    form.set('allow_late', form.get('allow_late') ? 'true' : 'false')
    if (!file) form.delete('attachment')
    setBusy(true)
    try {
      await api.post(`/api/courses/${courseId}/coursework`, form)
      onCreated()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not post the assignment.')
      setBusy(false)
    }
  }

  return (
    <form onSubmit={submit} className="form-grid">
      <ErrorNote>{error}</ErrorNote>
      <label className="field span-2">
        <span>Title</span>
        <input className="input" name="title" required maxLength={200} placeholder="Lab 4: LL(1) parser" autoFocus />
      </label>
      <label className="field span-2">
        <span>Instructions</span>
        <textarea className="textarea" name="instructions" maxLength={20000} placeholder="What should students hand in, and how will it be marked?" />
      </label>
      <label className="field">
        <span>Due</span>
        <input className="input" name="due_local" type="datetime-local" defaultValue={defaultDue()} required />
      </label>
      <label className="field">
        <span>Points <span className="hint">· optional</span></span>
        <input className="input mono" name="points" type="number" min={0} max={1000} placeholder="20" />
      </label>
      <label className="dropzone span-2">
        <Upload size={16} />
        <span>{file ? file.name : 'Attach a handout (PDF, DOCX, PPTX, code…) · optional'}</span>
        <input name="attachment" type="file" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
      </label>
      <label className="check span-2">
        <input type="checkbox" name="allow_late" defaultChecked /> Accept late submissions
      </label>
      <div className="span-2 row" style={{ justifyContent: 'flex-end' }}>
        <button className="btn primary" type="submit" disabled={busy}>{busy ? 'Posting…' : 'Post to class'}</button>
      </div>
    </form>
  )
}

export function TeacherCoursePage() {
  const { id = '' } = useParams()
  const navigate = useNavigate()
  const { data: course, setData: setCourse, error } = useLoad<Course>(`/api/courses/${id}`)
  const { data: work, loading, reload } = useLoad<TeacherWork[]>(`/api/courses/${id}/coursework`)
  const { data: members, reload: reloadMembers } = useLoad<Member[]>(`/api/courses/${id}/members`)
  const [tab, setTab] = useState<'work' | 'students'>('work')
  const [posting, setPosting] = useState(false)
  const [toast, setToast] = useState<string | null>(null)

  if (!course) return <main className="page">{error ? <ErrorNote>{error}</ErrorNote> : <Spinner />}</main>

  const copyCode = async () => {
    try {
      await navigator.clipboard.writeText(course.join_code ?? '')
      setToast('Class code copied.')
    } catch {
      setToast(`Class code: ${course.join_code}`)
    }
  }

  const rotate = async () => {
    if (!window.confirm('Make a new code? The old one stops working, but students who already joined stay in.')) return
    setCourse(await api.post<Course>(`/api/courses/${id}/join-code`))
  }

  const removeStudent = async (member: Member) => {
    if (!window.confirm(`Remove ${member.name} from this class?`)) return
    await api.del(`/api/courses/${id}/members/${member.id}`)
    await reloadMembers()
  }

  const deleteClass = async () => {
    if (!window.confirm(`Delete ${course.name}, all its assignments and every submission? This can't be undone.`)) return
    await api.del(`/api/courses/${id}`)
    navigate('/')
  }

  return (
    <main className="page">
      <nav className="crumbs" aria-label="Breadcrumb"><Link to="/">Classes</Link></nav>
      <div className="spread" style={{ alignItems: 'flex-end' }}>
        <div>
          <div className="row" style={{ gap: 8 }}>
            <span className="swatch" style={{ background: course.color, width: 10, height: 10 }} />
            {course.code && <span className="kicker">{course.code}</span>}
          </div>
          <h1 className="display" style={{ marginTop: 10, fontSize: 'clamp(32px, 4vw, 46px)' }}>{course.name}</h1>
        </div>
        <div style={{ textAlign: 'right' }}>
          <p className="kicker" style={{ marginBottom: 6 }}>Students join with</p>
          <span className="code-box">
            {course.join_code}
            <button className="btn ghost icon small" type="button" onClick={copyCode} aria-label="Copy class code"><Copy size={14} /></button>
            <button className="btn ghost icon small" type="button" onClick={rotate} aria-label="Make a new class code"><RefreshCw size={14} /></button>
          </span>
        </div>
      </div>
      {course.description && <p className="lede">{course.description}</p>}

      <div className="spread" style={{ marginTop: 30 }}>
        <div className="segmented" role="tablist">
          <button type="button" role="tab" aria-pressed={tab === 'work'} onClick={() => setTab('work')}>
            Assignments {work ? `· ${work.length}` : ''}
          </button>
          <button type="button" role="tab" aria-pressed={tab === 'students'} onClick={() => setTab('students')}>
            Students · {course.student_count}
          </button>
        </div>
        {tab === 'work' && (
          <button className="btn primary" type="button" onClick={() => setPosting(true)}>
            <Plus size={15} /> New assignment
          </button>
        )}
      </div>

      {tab === 'work' && (
        <div style={{ marginTop: 14 }}>
          {loading && !work && <Spinner />}
          {work && work.length === 0 && <Empty title="No assignments yet">Post one and every student in the class sees it on their Today page.</Empty>}
          {work && work.length > 0 && (
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr><th>Assignment</th><th>Due</th><th>Turned in</th><th>To review</th></tr>
                </thead>
                <tbody>
                  {work.map((w) => {
                    const pending = w.turned_in - w.returned
                    return (
                      <tr key={w.id} className="clickable" onClick={() => navigate(`/coursework/${w.id}`)}>
                        <td>
                          <Link to={`/coursework/${w.id}`} style={{ fontWeight: 500, textDecoration: 'none' }}>{w.title}</Link>
                          <span className="muted" style={{ display: 'block', fontSize: 12.5 }}>
                            Posted {shortDate(w.created_at)}{w.points !== null && ` · ${w.points} pts`}
                            {w.attachment_name && <> · <Paperclip size={11} /> {w.attachment_name}</>}
                          </span>
                        </td>
                        <td className="mono" style={{ fontSize: 12.5 }}>
                          {w.due_at ? <>{dueLabel(w.due_at)}<span className="muted" style={{ display: 'block' }}>{relative(w.due_at)}</span></> : '—'}
                        </td>
                        <td className="mono">{w.turned_in}/{w.total}{w.late > 0 && <span className="muted"> · {w.late} late</span>}</td>
                        <td className="mono" style={{ color: pending ? 'var(--accent)' : 'var(--muted)' }}>{pending || '—'}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {tab === 'students' && (
        <div style={{ marginTop: 14 }}>
          {members && members.length === 0 && (
            <Empty title="No students yet">Share the code <span className="mono">{course.join_code}</span>. Students enter it under Classes.</Empty>
          )}
          {members && members.length > 0 && (
            <table className="table">
              <thead><tr><th>Name</th><th>Email</th><th>Joined</th><th /></tr></thead>
              <tbody>
                {members.map((m) => (
                  <tr key={m.id}>
                    <td style={{ fontWeight: 500 }}>{m.name}</td>
                    <td className="muted">{m.email}</td>
                    <td className="mono" style={{ fontSize: 12.5 }}>{shortDate(m.joined_at)}</td>
                    <td style={{ textAlign: 'right' }}>
                      <button className="btn ghost small danger" type="button" onClick={() => removeStudent(m)}>Remove</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <button className="btn ghost small danger" type="button" style={{ marginTop: 30 }} onClick={deleteClass}>Delete this class</button>
        </div>
      )}

      <Sheet open={posting} title="New assignment" onClose={() => setPosting(false)}>
        <NewAssignment
          courseId={id}
          onCreated={() => {
            setPosting(false)
            setToast('Posted. Students will see it on their Today page.')
            void reload()
          }}
        />
      </Sheet>
      <Toast message={toast} onDone={() => setToast(null)} />
    </main>
  )
}
