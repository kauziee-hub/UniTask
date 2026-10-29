import { Link, useNavigate, useParams } from 'react-router-dom'
import { WorkRow } from '../../components/WorkRow'
import { Empty, ErrorNote, Spinner } from '../../components/ui'
import { api, type Course, type WorkItem } from '../../lib/api'
import { useLoad } from '../../lib/useLoad'

export function StudentCoursePage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const { data: course, error } = useLoad<Course>(`/api/courses/${id}`)
  const { data: work, loading } = useLoad<WorkItem[]>(`/api/courses/${id}/coursework`)

  const leave = async () => {
    if (!window.confirm(`Leave ${course?.name}? You'll stop seeing its assignments.`)) return
    await api.del(`/api/courses/${id}/members/me`)
    navigate('/classes')
  }

  if (!course) return <main className="page">{error ? <ErrorNote>{error}</ErrorNote> : <Spinner />}</main>

  const open = (work ?? []).filter((w) => w.status === 'assigned' || w.status === 'working')
  const finished = (work ?? []).filter((w) => !open.includes(w))

  return (
    <main className="page">
      <nav className="crumbs" aria-label="Breadcrumb"><Link to="/classes">Classes</Link></nav>
      <div className="spread" style={{ alignItems: 'flex-end' }}>
        <div>
          <div className="row" style={{ gap: 8 }}>
            <span className="swatch" style={{ background: course.color, width: 10, height: 10 }} />
            {course.code && <span className="kicker">{course.code}</span>}
            {course.source === 'teams' && <span className="pill teams">Synced from Teams</span>}
          </div>
          <h1 className="display" style={{ marginTop: 10, fontSize: 'clamp(32px, 4vw, 44px)' }}>{course.name}</h1>
          {course.teacher_name && <p className="muted" style={{ marginTop: 6 }}>{course.teacher_name}</p>}
        </div>
        {course.my_role === 'student' && <button className="btn ghost small danger" type="button" onClick={leave}>Leave class</button>}
      </div>
      {course.description && <p className="lede">{course.description}</p>}

      <div className="section-head"><h2>Open</h2><span className="aside">{open.length}</span></div>
      {loading && !work && <Spinner />}
      {work && (open.length ? <ul className="list">{open.map((w) => <WorkRow key={w.id} item={w} showReason />)}</ul> : <Empty title="Nothing open in this class" />)}

      {finished.length > 0 && (
        <>
          <div className="section-head"><h2>Done</h2><span className="aside">{finished.length}</span></div>
          <ul className="list">{finished.map((w) => <WorkRow key={w.id} item={w} />)}</ul>
        </>
      )}
    </main>
  )
}
