import { useState, type FormEvent } from 'react'
import { ExternalLink, FileText, Paperclip, Trash2, Upload } from 'lucide-react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ErrorNote, SourcePill, Spinner, StatusPill } from '../../components/ui'
import { api, openFile, type WorkItem } from '../../lib/api'
import { dueLabel, minutesLabel, relative } from '../../lib/format'
import { useLoad } from '../../lib/useLoad'

const EFFORTS = [15, 30, 60, 120, 180, 300, 480]

function TurnIn({ item, onSaved }: { item: WorkItem; onSaved: (item: WorkItem) => void }) {
  const [file, setFile] = useState<File | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const closed = item.due_at && new Date(item.due_at) < new Date() && !item.allow_late

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    if (!file) form.delete('file')
    setBusy(true)
    setError(null)
    try {
      onSaved(await api.post<WorkItem>(`/api/work/${item.id}/turn-in`, form))
      setFile(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not turn in.')
    } finally {
      setBusy(false)
    }
  }

  if (closed) return <div className="note error">This assignment closed {relative(item.due_at!)} and doesn't accept late work.</div>

  return (
    <form onSubmit={submit} style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <ErrorNote>{error}</ErrorNote>
      <label className="dropzone">
        <Upload size={16} />
        <span>{file ? file.name : item.file_name ? `Replace ${item.file_name}` : 'Attach your work (PDF, DOCX, code, images, zip · 15 MB)'}</span>
        <input name="file" type="file" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
      </label>
      <label className="field">
        <span>Note to your teacher <span className="hint">· optional</span></span>
        <textarea className="textarea" name="text" defaultValue={item.text ?? ''} style={{ minHeight: 80 }} maxLength={20000} />
      </label>
      <button className="btn primary" type="submit" disabled={busy}>
        {busy ? 'Uploading…' : item.due_at && new Date(item.due_at) < new Date() ? 'Turn in late' : 'Turn in'}
      </button>
    </form>
  )
}

export function WorkDetailPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const { data: item, setData, error, loading } = useLoad<WorkItem>(`/api/work/${id}`)
  const [actionError, setActionError] = useState<string | null>(null)

  const patch = async (body: Record<string, unknown>) => {
    setActionError(null)
    try {
      setData(await api.patch<WorkItem>(`/api/work/${id}`, body))
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Could not update.')
    }
  }

  const undo = async () => {
    try {
      setData(await api.post<WorkItem>(`/api/work/${id}/undo-turn-in`))
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Could not undo.')
    }
  }

  const remove = async () => {
    if (!window.confirm('Delete this task?')) return
    await api.del(`/api/work/${id}`)
    navigate('/work')
  }

  if (!item) {
    return (
      <main className="page narrow">
        {loading ? <Spinner /> : <ErrorNote>{error ?? 'Not found.'}</ErrorNote>}
      </main>
    )
  }

  const done = item.status === 'turned_in' || item.status === 'returned'
  const late = done && item.due_at && item.submitted_at && item.submitted_at > item.due_at

  return (
    <main className="page">
      <nav className="crumbs" aria-label="Breadcrumb">
        <Link to="/work">Deadlines</Link>
        {item.course && <><span>/</span><Link to={`/classes/${item.course.id}`}>{item.course.name}</Link></>}
      </nav>

      <div className="split">
        <div>
          <div className="row" style={{ gap: 8 }}>
            <SourcePill source={item.source} />
            <StatusPill status={item.status} late={Boolean(late)} />
            {item.removed_at_source && <span className="pill accent">Removed from Teams</span>}
          </div>
          <h1 className="display" style={{ marginTop: 12, fontSize: 'clamp(30px, 4vw, 42px)' }}>{item.title}</h1>

          <dl className="facts">
            <div>
              <dt>Due</dt>
              <dd className="mono" style={{ color: !done && ['overdue', 'now'].includes(item.priority.tier) ? 'var(--accent)' : undefined }}>
                {item.due_at ? dueLabel(item.due_at) : 'No due date'}
              </dd>
            </div>
            {item.due_at && !done && <div><dt>Time left</dt><dd className="mono">{relative(item.due_at)}</dd></div>}
            {item.points !== null && <div><dt>Points</dt><dd className="mono">{item.grade !== null ? `${item.grade} / ${item.points}` : item.points}</dd></div>}
            {done && item.submitted_at && <div><dt>Turned in</dt><dd className="mono">{dueLabel(item.submitted_at)}</dd></div>}
          </dl>

          {!done && <p className="lede" style={{ marginTop: 0 }}>{item.priority.reason}.</p>}

          <h2 className="kicker" style={{ marginTop: 28, marginBottom: 10 }}>Instructions</h2>
          {item.instructions ? <p className="prose">{item.instructions}</p> : <p className="muted">No instructions were given.</p>}

          {item.attachment_name && (
            <div style={{ marginTop: 18 }}>
              <button className="file-chip" type="button" onClick={() => openFile(`/api/coursework/${item.id}/attachment`)}>
                <Paperclip size={14} /> {item.attachment_name}
              </button>
            </div>
          )}

          {item.changes.length > 0 && (
            <>
              <h2 className="kicker" style={{ marginTop: 30, marginBottom: 6 }}>History from Teams</h2>
              <ul className="list">
                {item.changes.map((c) => (
                  <li key={c.id} className="change">
                    <span className="kind muted">{relative(c.detected_at)}</span>
                    <span>
                      {c.kind === 'due_changed' && (
                        <>Due date moved: <span className="strike">{c.old_value ? dueLabel(c.old_value) : 'none'}</span> → {c.new_value ? dueLabel(c.new_value) : 'none'}</>
                      )}
                      {c.kind === 'title_changed' && <>Renamed from “{c.old_value}”</>}
                      {c.kind === 'removed' && <>Removed from Teams by the teacher</>}
                    </span>
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>

        <aside style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <ErrorNote>{actionError}</ErrorNote>

          {item.status === 'returned' && (
            <div className="panel">
              <p className="kicker">Graded</p>
              <p className="title" style={{ marginTop: 6 }}>
                {item.grade !== null ? <>{item.grade}{item.points !== null && <span className="muted"> / {item.points}</span>}</> : 'Returned'}
              </p>
              {item.feedback && <p className="prose" style={{ marginTop: 10 }}>{item.feedback}</p>}
            </div>
          )}

          <div className="panel">
            {item.source === 'teams' && (
              <>
                <p style={{ fontWeight: 500 }}>{done ? 'Turned in on Teams' : 'Submit this on Teams'}</p>
                <p className="muted" style={{ fontSize: 13, margin: '6px 0 14px' }}>
                  Your teacher collects this in Teams. Once you turn it in there, UniTask updates on the next sync.
                </p>
                {item.external_url && (
                  <a className="btn teams" href={item.external_url} target="_blank" rel="noreferrer" style={{ width: '100%' }}>
                    Open in Teams <ExternalLink size={14} />
                  </a>
                )}
              </>
            )}

            {item.source === 'unitask' && (
              item.status === 'turned_in' ? (
                <>
                  <p style={{ fontWeight: 500 }}>Turned in {item.submitted_at && relative(item.submitted_at)}</p>
                  {item.file_name && item.submission_id && (
                    <button className="file-chip" type="button" style={{ marginTop: 12 }} onClick={() => openFile(`/api/submissions/${item.submission_id}/file`)}>
                      <FileText size={14} /> {item.file_name}
                    </button>
                  )}
                  {item.text && <p className="prose" style={{ marginTop: 10, fontSize: 13 }}>{item.text}</p>}
                  <button className="btn" type="button" style={{ marginTop: 14, width: '100%' }} onClick={undo}>Undo turn in</button>
                </>
              ) : item.status === 'returned' ? (
                item.file_name && item.submission_id ? (
                  <button className="file-chip" type="button" onClick={() => openFile(`/api/submissions/${item.submission_id}/file`)}>
                    <FileText size={14} /> {item.file_name}
                  </button>
                ) : <p className="muted">Returned by your teacher.</p>
              ) : (
                <TurnIn item={item} onSaved={setData} />
              )
            )}

            {item.source === 'personal' && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                <button className="btn primary" type="button" onClick={() => patch({ status: done ? 'assigned' : 'done' })}>
                  {done ? 'Mark as not done' : 'Mark as done'}
                </button>
                <button className="btn ghost danger" type="button" onClick={remove}><Trash2 size={14} /> Delete task</button>
              </div>
            )}
          </div>

          {!done && (
            <div className="panel">
              <p style={{ fontWeight: 500 }}>How long will this take you?</p>
              <p className="muted" style={{ fontSize: 13, margin: '4px 0 12px' }}>
                Used to rank this against everything else. Currently {minutesLabel(item.priority.effort_minutes)}
                {item.effort_minutes === null && ' (a guess)'}.
              </p>
              <div className="row" style={{ gap: 6 }}>
                {EFFORTS.map((m) => (
                  <button
                    key={m}
                    type="button"
                    className="btn small"
                    aria-pressed={item.effort_minutes === m}
                    style={item.effort_minutes === m ? { background: 'var(--ink)', color: 'var(--paper)', borderColor: 'var(--ink)' } : undefined}
                    onClick={() => patch({ effort_minutes: m })}
                  >
                    {minutesLabel(m)}
                  </button>
                ))}
              </div>
              {item.source !== 'personal' && item.status === 'assigned' && (
                <button className="btn ghost small" type="button" style={{ marginTop: 12 }} onClick={() => patch({ status: 'working' })}>
                  I've started this
                </button>
              )}
            </div>
          )}
        </aside>
      </div>
    </main>
  )
}
