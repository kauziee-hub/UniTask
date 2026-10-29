import { useState, type FormEvent } from 'react'
import { FileText, Paperclip } from 'lucide-react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { Empty, ErrorNote, Spinner, StatusPill } from '../../components/ui'
import { api, openFile, type SubmissionRow, type TeacherWork } from '../../lib/api'
import { dueLabel, relative } from '../../lib/format'
import { useLoad } from '../../lib/useLoad'

function GradeForm({ row, points, onSaved }: { row: SubmissionRow; points: number | null; onSaved: (row: SubmissionRow) => void }) {
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    const grade = String(form.get('grade') ?? '')
    setBusy(true)
    setError(null)
    try {
      onSaved(
        await api.patch<SubmissionRow>(`/api/submissions/${row.id}/grade`, {
          grade: grade === '' ? null : Number(grade),
          feedback: form.get('feedback') || null,
          return_to_student: true,
        }),
      )
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save the grade.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={submit} style={{ display: 'grid', gridTemplateColumns: '110px 1fr auto', gap: 10, alignItems: 'end', marginTop: 14 }}>
      <label className="field">
        <span>Grade{points !== null && <span className="hint"> / {points}</span>}</span>
        <input className="input mono" name="grade" type="number" min={0} max={points ?? 1000} defaultValue={row.grade ?? ''} />
      </label>
      <label className="field">
        <span>Feedback</span>
        <input className="input" name="feedback" defaultValue={row.feedback ?? ''} maxLength={4000} placeholder="What went well, what to fix" />
      </label>
      <button className="btn primary" type="submit" disabled={busy}>{row.status === 'returned' ? 'Update' : 'Return'}</button>
      {error && <div style={{ gridColumn: '1 / -1' }}><ErrorNote>{error}</ErrorNote></div>}
    </form>
  )
}

export function CourseworkReviewPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const { data: work, error } = useLoad<TeacherWork>(`/api/coursework/${id}`)
  const { data: rows, setData: setRows, loading } = useLoad<SubmissionRow[]>(`/api/coursework/${id}/submissions`)
  const [openRow, setOpenRow] = useState<number | null>(null)

  if (!work) return <main className="page">{error ? <ErrorNote>{error}</ErrorNote> : <Spinner />}</main>

  const remove = async () => {
    if (!window.confirm(`Delete “${work.title}” and all its submissions?`)) return
    await api.del(`/api/coursework/${id}`)
    navigate(`/classes/${work.course_id}`)
  }

  const waiting = (rows ?? []).filter((r) => r.status === 'turned_in').length

  return (
    <main className="page">
      <nav className="crumbs" aria-label="Breadcrumb">
        <Link to="/">Classes</Link><span>/</span><Link to={`/classes/${work.course_id}`}>{work.course_name}</Link>
      </nav>
      <h1 className="display" style={{ fontSize: 'clamp(30px, 4vw, 42px)' }}>{work.title}</h1>

      <dl className="facts">
        <div><dt>Due</dt><dd className="mono">{work.due_at ? dueLabel(work.due_at) : 'No due date'}</dd></div>
        <div><dt>Turned in</dt><dd className="mono">{work.turned_in} of {work.total}</dd></div>
        <div><dt>Late</dt><dd className="mono">{work.late}</dd></div>
        <div><dt>Waiting for you</dt><dd className="mono" style={{ color: waiting ? 'var(--accent)' : undefined }}>{waiting}</dd></div>
      </dl>

      {work.instructions && <p className="prose">{work.instructions}</p>}
      {work.attachment_name && (
        <button className="file-chip" type="button" style={{ marginTop: 14 }} onClick={() => openFile(`/api/coursework/${work.id}/attachment`)}>
          <Paperclip size={14} /> {work.attachment_name}
        </button>
      )}

      <div className="section-head"><h2>Submissions</h2><span className="aside">click a row to grade</span></div>
      {loading && !rows && <Spinner />}
      {rows && rows.length === 0 && <Empty title="No students in this class yet" />}
      {rows && rows.length > 0 && (
        <ul className="list">
          {rows.map((row) => {
            const expanded = openRow === row.student.id
            const submitted = row.status === 'turned_in' || row.status === 'returned'
            return (
              <li key={row.student.id} style={{ borderBottom: '1px solid var(--rule)', padding: '12px 0' }}>
                <button
                  type="button"
                  onClick={() => setOpenRow(expanded ? null : row.student.id)}
                  disabled={!submitted}
                  aria-expanded={expanded}
                  aria-label={`${row.student.name}: ${submitted ? 'open submission' : 'not turned in'}`}
                  style={{ all: 'unset', display: 'grid', gridTemplateColumns: 'minmax(0,1fr) auto auto', gap: 14, width: '100%', cursor: submitted ? 'pointer' : 'default', alignItems: 'center' }}
                >
                  <span>
                    <span style={{ fontWeight: 500 }}>{row.student.name}</span>
                    <span className="muted" style={{ display: 'block', fontSize: 12.5 }}>{row.student.email}</span>
                  </span>
                  <span className="mono muted" style={{ fontSize: 12.5 }}>
                    {row.submitted_at ? relative(row.submitted_at) : row.status === 'working' ? 'started' : 'not turned in'}
                  </span>
                  <span style={{ minWidth: 110, textAlign: 'right' }}>
                    {row.status === 'returned' && row.grade !== null ? (
                      <span className="mono">{row.grade}{work.points !== null && <span className="muted">/{work.points}</span>}</span>
                    ) : (
                      <StatusPill status={row.status} late={row.late} />
                    )}
                  </span>
                </button>
                {expanded && submitted && (
                  <div style={{ marginTop: 12, paddingLeft: 2 }}>
                    {row.late && <span className="pill warn" style={{ marginBottom: 8 }}>Late</span>}
                    {row.file_name && row.id && (
                      <button className="file-chip" type="button" onClick={() => openFile(`/api/submissions/${row.id}/file`)}>
                        <FileText size={14} /> {row.file_name}
                      </button>
                    )}
                    {row.text && <p className="prose" style={{ marginTop: 10, fontSize: 13.5 }}>{row.text}</p>}
                    <GradeForm
                      row={row}
                      points={work.points}
                      onSaved={(saved) => {
                        setRows((rows ?? []).map((r) => (r.student.id === saved.student.id ? saved : r)))
                        setOpenRow(null)
                      }}
                    />
                  </div>
                )}
              </li>
            )
          })}
        </ul>
      )}

      <button className="btn ghost small danger" type="button" style={{ marginTop: 30 }} onClick={remove}>Delete assignment</button>
    </main>
  )
}
