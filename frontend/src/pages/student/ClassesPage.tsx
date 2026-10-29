import { useState, type CSSProperties, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { Empty, ErrorNote, Spinner } from '../../components/ui'
import { api, type Course } from '../../lib/api'
import { useLoad } from '../../lib/useLoad'

export function ClassCard({ course, href }: { course: Course; href: string }) {
  return (
    <Link to={href} className="class-card" style={{ '--class-color': course.color } as CSSProperties}>
      <span className="row" style={{ gap: 6, marginBottom: 8 }}>
        {course.code && <span className="kicker">{course.code}</span>}
        {course.source === 'teams' && <span className="pill teams">Teams</span>}
      </span>
      <h3>{course.name}</h3>
      {course.teacher_name && <p className="muted" style={{ marginTop: 6, fontSize: 13 }}>{course.teacher_name}</p>}
      <div className="foot">
        {course.my_role === 'teacher' ? (
          <>
            <span>{course.student_count} student{course.student_count === 1 ? '' : 's'}</span>
            <span style={{ color: course.open_count ? 'var(--accent)' : undefined }}>
              {course.open_count ? `${course.open_count} to review` : 'Nothing to review'}
            </span>
          </>
        ) : (
          <span style={{ color: course.open_count ? 'var(--ink)' : undefined }}>
            {course.open_count ? `${course.open_count} open` : 'All done'}
          </span>
        )}
      </div>
    </Link>
  )
}

export function ClassesPage() {
  const { data, error, loading, reload } = useLoad<Course[]>('/api/courses')
  const [joinError, setJoinError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const join = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const form = event.currentTarget
    const code = String(new FormData(form).get('code')).trim()
    setBusy(true)
    setJoinError(null)
    try {
      await api.post('/api/courses/join', { code })
      form.reset()
      await reload()
    } catch (err) {
      setJoinError(err instanceof Error ? err.message : 'Could not join.')
    } finally {
      setBusy(false)
    }
  }

  const unitask = (data ?? []).filter((c) => c.source === 'unitask')
  const teams = (data ?? []).filter((c) => c.source === 'teams')

  return (
    <main className="page">
      <p className="kicker">Classes</p>
      <h1 className="title" style={{ marginTop: 8 }}>Your classes</h1>

      <form onSubmit={join} className="row" style={{ marginTop: 22, alignItems: 'flex-end' }}>
        <label className="field" style={{ width: 220 }}>
          <span>Join with a class code</span>
          <input className="input mono" name="code" required minLength={4} maxLength={12} placeholder="K7Q2XM" style={{ textTransform: 'uppercase', letterSpacing: '0.15em' }} />
        </label>
        <button className="btn primary" type="submit" disabled={busy}>{busy ? 'Joining…' : 'Join class'}</button>
      </form>
      <div style={{ marginTop: 10 }}><ErrorNote>{joinError}</ErrorNote></div>

      <ErrorNote>{error}</ErrorNote>
      {!data && loading && <Spinner />}

      {data && (
        <>
          <div className="section-head"><h2>UniTask classes</h2><span className="aside">{unitask.length}</span></div>
          {unitask.length ? (
            <div className="classes">{unitask.map((c) => <ClassCard key={c.id} course={c} href={`/classes/${c.id}`} />)}</div>
          ) : (
            <Empty title="No classes yet">Ask your teacher for the 6-letter class code.</Empty>
          )}

          <div className="section-head">
            <h2>From Microsoft Teams</h2>
            <Link className="aside" to="/connections">Teams sync →</Link>
          </div>
          {teams.length ? (
            <div className="classes">{teams.map((c) => <ClassCard key={c.id} course={c} href={`/classes/${c.id}`} />)}</div>
          ) : (
            <Empty title="No Teams classes synced">Connect Teams and your class teams appear here automatically.</Empty>
          )}
        </>
      )}
    </main>
  )
}
