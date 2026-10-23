import { useMemo, useState } from 'react'
import type { CSSProperties } from 'react'
import { ArrowRight, CalendarClock, Check, CheckCircle2, Circle, Clock3, Plus, Search, Sparkles, Target, TrendingUp } from 'lucide-react'
import { Link } from 'react-router-dom'
import { useAppData } from '../data/useAppData'
import { dateInDays, daysUntilDue, formatDueDate, type Assignment } from '../data/sampleData'
import { MetricCard } from '../components/MetricCard'
import { AssignmentEditor } from '../components/AssignmentEditor'

type Filter = 'All tasks' | 'Due soon' | 'In progress'

function AssignmentRow({ assignment, onEdit, onComplete }: { assignment: Assignment; onEdit: () => void; onComplete: () => void }) {
  const { subjects } = useAppData()
  const subject = subjects.find((item) => item.id === assignment.subjectId)
  const days = daysUntilDue(assignment.dueDate)
  const StatusIcon = assignment.status === 'In progress' ? Clock3 : assignment.status === 'Completed' ? CheckCircle2 : Circle
  return (
    <div className="assignment-item">
      <div className="assignment-main">
        <StatusIcon size={15} color={assignment.status === 'In progress' ? 'var(--primary)' : assignment.status === 'Completed' ? 'var(--success)' : 'var(--line-strong)'} />
        <span className="subject-dot" style={{ '--dot-color': subject?.color } as CSSProperties} />
        <div style={{ minWidth: 0 }}>
          <div className="assignment-title">{assignment.title}</div>
          <div className="assignment-subject">{subject?.name ?? 'Unassigned'} <span aria-hidden="true">·</span> {assignment.platform}</div>
        </div>
      </div>
      <div className="assignment-meta">
        <span className={`due-label${days <= 1 && assignment.status !== 'Completed' ? ' urgent' : ''}`}>
          {assignment.status === 'Completed' ? 'Complete' : days < 0 ? `Overdue ${Math.abs(days)}d` : `Due ${formatDueDate(assignment.dueDate)}`}
        </span>
        <span className={`status-pill${assignment.status === 'In progress' ? ' in-progress' : assignment.status === 'Completed' ? ' complete' : ''}`}>{assignment.status}</span>
        <div className="row-actions">
          <button className="action-button" type="button" onClick={onComplete}>{assignment.status === 'Completed' ? 'Reopen' : 'Complete'}</button>
          <button className="action-button" type="button" onClick={onEdit}>Edit</button>
        </div>
      </div>
    </div>
  )
}

export function DashboardPage() {
  const { assignments, subjects, completeAssignment } = useAppData()
  const [filter, setFilter] = useState<Filter>('All tasks')
  const [search, setSearch] = useState('')
  const [editing, setEditing] = useState<Assignment | undefined>()
  const [adding, setAdding] = useState(false)
  const today = new Date().toLocaleDateString(undefined, { weekday: 'long', month: 'long', day: 'numeric' })
  const activeAssignments = assignments.filter((assignment) => assignment.status !== 'Completed')
  const overdueCount = activeAssignments.filter((assignment) => daysUntilDue(assignment.dueDate) < 0).length
  const dueTodayCount = activeAssignments.filter((assignment) => daysUntilDue(assignment.dueDate) === 0).length
  const dueWeekCount = activeAssignments.filter((assignment) => daysUntilDue(assignment.dueDate) >= 0 && daysUntilDue(assignment.dueDate) <= 6).length
  const filteredAssignments = useMemo(() => assignments.filter((assignment) => {
    const subject = subjects.find((item) => item.id === assignment.subjectId)
    const days = daysUntilDue(assignment.dueDate)
    const matchesFilter = filter === 'All tasks'
      || (filter === 'Due soon' && assignment.status !== 'Completed' && days >= 0 && days <= 2)
      || (filter === 'In progress' && assignment.status === 'In progress')
    const matchesSearch = `${assignment.title} ${subject?.name ?? ''} ${assignment.platform}`.toLowerCase().includes(search.toLowerCase())
    return matchesFilter && matchesSearch
  }), [assignments, filter, search, subjects])
  const focusAssignments = activeAssignments
    .toSorted((a, b) => daysUntilDue(a.dueDate) - daysUntilDue(b.dueDate))
    .slice(0, 2)
  const weekWorkload = Array.from({ length: 7 }, (_, offset) => {
    const count = activeAssignments.filter((assignment) => daysUntilDue(assignment.dueDate) === offset).length
    return { day: dateInDays(offset).toLocaleDateString(undefined, { weekday: 'short' }), count }
  })
  const maxWorkload = Math.max(1, ...weekWorkload.map((day) => day.count))

  const startAdd = () => {
    if (subjects.length === 0) {
      window.alert('Add a subject before creating an assignment.')
      return
    }
    setAdding(true)
  }

  return (
    <div className="content">
      <div className="page-heading">
        <div>
          <div className="eyebrow">{today}</div>
          <h1 className="page-title">Good morning, Alex <span aria-hidden="true">✦</span></h1>
          <div className="page-subtitle">Your demo workspace is saved in this browser.</div>
        </div>
        <div className="heading-actions">
          <Link className="secondary-button" to="/calendar"><CalendarClock size={15} /> View calendar</Link>
          <button className="primary-button" type="button" onClick={startAdd}><Plus size={15} /> Add assignment</button>
        </div>
      </div>

      <section className="metric-grid" aria-label="Academic overview">
        <MetricCard label="Pending assignments" value={activeAssignments.length} footnote={`Across ${subjects.length} subjects`} icon={CheckCircle2} />
        <MetricCard label="Due today" value={dueTodayCount} footnote="Based on your task list" icon={CalendarClock} tone="amber" />
        <MetricCard label="Due this week" value={dueWeekCount} footnote={`${assignments.filter((item) => item.status === 'Completed').length} completed overall`} icon={TrendingUp} tone="teal" />
        <MetricCard label="Overdue" value={overdueCount} footnote={overdueCount ? 'Needs your attention' : 'You’re all caught up'} icon={Target} tone="red" />
      </section>

      <div className="dashboard-grid">
        <div className="left-stack">
          <section className="panel">
            <div className="section-heading">
              <div><h2 className="section-title">Upcoming assignments</h2><div className="section-note">Manage work from across your subjects</div></div>
              <Link className="text-link" to="/assignments">See all <ArrowRight size={13} /></Link>
            </div>
            <div className="filter-row" role="group" aria-label="Filter assignments">
              {(['All tasks', 'Due soon', 'In progress'] as const).map((item) => (
                <button key={item} type="button" className={`filter-button${filter === item ? ' selected' : ''}`} onClick={() => setFilter(item)}>{item}</button>
              ))}
            </div>
            <label className="search-box" style={{ width: '100%', marginBottom: 11 }}>
              <Search size={15} />
              <input aria-label="Filter assignments by search" placeholder="Filter by title, subject, or platform..." value={search} onChange={(event) => setSearch(event.target.value)} />
            </label>
            <div className="assignment-list">
              {filteredAssignments.length > 0
                ? filteredAssignments.slice(0, 5).map((assignment) => <AssignmentRow key={assignment.id} assignment={assignment} onEdit={() => setEditing(assignment)} onComplete={() => completeAssignment(assignment.id)} />)
                : <div className="empty-state"><Check size={20} /><p>No assignments match this view.</p></div>}
            </div>
          </section>

          <section className="panel">
            <div className="section-heading">
              <div><h2 className="section-title">Your workload</h2><div className="section-note">Open assignments due in the next 7 days</div></div>
              <span className="status-pill in-progress"><TrendingUp size={11} /> This week</span>
            </div>
            <div className="workload-chart" aria-label="Assignments due each day for the next week">
              {weekWorkload.map(({ day, count }, index) => (
                <div className="workload-day" key={`${day}-${index}`}>
                  <div className="bar-track"><div className={`bar${index === 0 ? ' today' : ''}`} style={{ height: `${Math.max(7, count / maxWorkload * 100)}%` }} title={`${count} assignments`} /></div>
                  <span className="day-label">{day} ({count})</span>
                </div>
              ))}
            </div>
          </section>
        </div>

        <div className="right-stack">
          <section className="panel priority-panel">
            <div className="section-heading">
              <div><h2 className="section-title">Focus next</h2><div className="section-note">Ranked by nearest deadline</div></div>
              <Sparkles size={17} className="priority-icon" />
            </div>
            {focusAssignments.length ? focusAssignments.map((assignment) => {
              const subject = subjects.find((item) => item.id === assignment.subjectId)
              const days = daysUntilDue(assignment.dueDate)
              return <article className="priority-card" key={assignment.id}><div className="priority-card-title">{assignment.title}</div><div className="priority-reason">{subject?.code ?? 'Subject'} · {days < 0 ? 'Overdue' : days === 0 ? 'Due today' : `Due in ${days} day${days === 1 ? '' : 's'}`}</div><div className="priority-due"><Clock3 size={12} /> Due {formatDueDate(assignment.dueDate)}</div></article>
            }) : <div className="empty-state"><CheckCircle2 size={20} /><p>Everything is complete.</p></div>}
            <Link className="text-link" style={{ marginTop: 15 }} to="/assistant">Plan my week <ArrowRight size={13} /></Link>
          </section>

          <section className="panel">
            <div className="section-heading"><div><h2 className="section-title">Subject workload</h2><div className="section-note">Open tasks by subject</div></div></div>
            <div className="subject-list">
              {subjects.map((subject) => {
                const count = activeAssignments.filter((assignment) => assignment.subjectId === subject.id).length
                return <div className="subject-row" key={subject.id}><span className="subject-dot" style={{ '--dot-color': subject.color } as CSSProperties} /><div className="subject-info"><div className="subject-name">{subject.name}</div><div className="progress-track"><div className="progress-fill" style={{ width: `${Math.min(100, count * 20)}%`, '--bar-color': subject.color } as CSSProperties} /></div></div><span className="subject-count">{count}</span></div>
              })}
              {subjects.length === 0 && <div className="empty-state"><p>Add subjects to see workload.</p></div>}
            </div>
          </section>
        </div>
      </div>
      {adding && <AssignmentEditor onClose={() => setAdding(false)} />}
      {editing && <AssignmentEditor assignment={editing} onClose={() => setEditing(undefined)} />}
    </div>
  )
}
