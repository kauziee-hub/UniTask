import { useMemo, useState, type FormEvent } from 'react'
import { Plus } from 'lucide-react'
import { WorkRow } from '../../components/WorkRow'
import { Empty, ErrorNote, Sheet, Spinner } from '../../components/ui'
import { api, type Course, type WorkItem } from '../../lib/api'
import { bucketFor, fromLocalInput, type Bucket } from '../../lib/format'
import { useLoad } from '../../lib/useLoad'

const ORDER: Bucket[] = ['Overdue', 'Today', 'Tomorrow', 'This week', 'Later', 'No due date']
const FILTERS = [
  { key: 'all', label: 'Everything' },
  { key: 'teams', label: 'From Teams' },
  { key: 'unitask', label: 'UniTask classes' },
  { key: 'personal', label: 'My tasks' },
] as const
const EFFORT = [
  { value: '', label: 'Not sure' },
  { value: '30', label: '30 min' },
  { value: '60', label: '1 hour' },
  { value: '120', label: '2 hours' },
  { value: '240', label: '4 hours' },
  { value: '480', label: 'A full day' },
]

function NewTask({ courses, onCreated }: { courses: Course[]; onCreated: () => void }) {
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    setBusy(true)
    try {
      await api.post('/api/work', {
        title: form.get('title'),
        due_at: fromLocalInput(String(form.get('due_at') ?? '')),
        course_id: form.get('course_id') ? Number(form.get('course_id')) : null,
        effort_minutes: form.get('effort') ? Number(form.get('effort')) : null,
        notes: form.get('notes') || null,
      })
      onCreated()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={submit} className="form-grid">
      <ErrorNote>{error}</ErrorNote>
      <label className="field span-2">
        <span>What needs doing?</span>
        <input className="input" name="title" required maxLength={200} placeholder="Revise normalization for CAT 2" autoFocus />
      </label>
      <label className="field">
        <span>Due</span>
        <input className="input" name="due_at" type="datetime-local" />
      </label>
      <label className="field">
        <span>How long will it take?</span>
        <select className="select" name="effort" defaultValue="">
          {EFFORT.map((e) => <option key={e.value} value={e.value}>{e.label}</option>)}
        </select>
      </label>
      <label className="field span-2">
        <span>Class <span className="hint">· optional</span></span>
        <select className="select" name="course_id" defaultValue="">
          <option value="">None</option>
          {courses.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
      </label>
      <label className="field span-2">
        <span>Notes <span className="hint">· optional</span></span>
        <textarea className="textarea" name="notes" style={{ minHeight: 70 }} maxLength={4000} />
      </label>
      <div className="span-2 row" style={{ justifyContent: 'flex-end' }}>
        <button className="btn primary" type="submit" disabled={busy}>{busy ? 'Saving…' : 'Add task'}</button>
      </div>
    </form>
  )
}

export function WorkPage() {
  const { data, error, loading, reload } = useLoad<WorkItem[]>('/api/work')
  const { data: courses } = useLoad<Course[]>('/api/courses')
  const [filter, setFilter] = useState<(typeof FILTERS)[number]['key']>('all')
  const [adding, setAdding] = useState(false)
  const [showDone, setShowDone] = useState(false)

  const { groups, done } = useMemo(() => {
    const items = (data ?? []).filter((i) => filter === 'all' || i.source === filter)
    const finished = items.filter((i) => i.status === 'turned_in' || i.status === 'returned')
    const open = items.filter((i) => !finished.includes(i) && !i.removed_at_source && i.priority.tier !== 'missed')
    const grouped = new Map<Bucket, WorkItem[]>()
    for (const item of open) {
      const bucket = bucketFor(item.due_at)
      grouped.set(bucket, [...(grouped.get(bucket) ?? []), item])
    }
    const missed = items.filter((i) => !finished.includes(i) && (i.removed_at_source || i.priority.tier === 'missed'))
    return { groups: ORDER.filter((b) => grouped.has(b)).map((b) => [b, grouped.get(b)!] as const), done: [...missed, ...finished] }
  }, [data, filter])

  return (
    <main className="page">
      <div className="spread">
        <div>
          <p className="kicker">Deadlines</p>
          <h1 className="title" style={{ marginTop: 8 }}>Everything due, in one list</h1>
        </div>
        <button className="btn primary" type="button" onClick={() => setAdding(true)}>
          <Plus size={15} /> Add a task
        </button>
      </div>

      <div className="segmented" role="group" aria-label="Filter by source" style={{ marginTop: 22 }}>
        {FILTERS.map((f) => (
          <button key={f.key} type="button" aria-pressed={filter === f.key} onClick={() => setFilter(f.key)}>
            {f.label}
          </button>
        ))}
      </div>

      <ErrorNote>{error}</ErrorNote>
      {!data && loading && <div style={{ marginTop: 24 }}><Spinner /></div>}

      {data && groups.length === 0 && (
        <Empty title="Nothing open here">
          {filter === 'teams' ? 'Connect Teams from Teams sync to pull your assignments in.' : 'Add a task, or join a class with a code.'}
        </Empty>
      )}

      {groups.map(([bucket, items]) => (
        <section key={bucket}>
          <div className="section-head">
            <h2 style={bucket === 'Overdue' ? { color: 'var(--accent)' } : undefined}>{bucket}</h2>
            <span className="aside">{items.length}</span>
          </div>
          <ul className="list">{items.map((item) => <WorkRow key={item.id} item={item} />)}</ul>
        </section>
      ))}

      {done.length > 0 && (
        <section>
          <div className="section-head">
            <h2>Done, closed or removed</h2>
            <button className="btn ghost small" type="button" onClick={() => setShowDone(!showDone)}>
              {showDone ? 'Hide' : `Show ${done.length}`}
            </button>
          </div>
          {showDone && <ul className="list">{done.map((item) => <WorkRow key={item.id} item={item} />)}</ul>}
        </section>
      )}

      <Sheet open={adding} title="Add a task" onClose={() => setAdding(false)}>
        <NewTask
          courses={courses ?? []}
          onCreated={() => {
            setAdding(false)
            void reload()
          }}
        />
      </Sheet>
    </main>
  )
}
