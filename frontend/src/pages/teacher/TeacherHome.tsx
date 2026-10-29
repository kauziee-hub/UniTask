import { useState, type FormEvent } from 'react'
import { Plus } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { Empty, ErrorNote, Sheet, Spinner } from '../../components/ui'
import { api, type Course } from '../../lib/api'
import { useAuth } from '../../lib/auth'
import { useLoad } from '../../lib/useLoad'
import { ClassCard } from '../student/ClassesPage'

const COLORS = ['#2f5d50', '#b5562b', '#5b5fc7', '#7a4f9a', '#2d6a8e', '#8a6d1f', '#a23b5a', '#3f3d38']

function NewClass({ onCreated }: { onCreated: (course: Course) => void }) {
  const [color, setColor] = useState(COLORS[0])
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    setBusy(true)
    try {
      onCreated(
        await api.post<Course>('/api/courses', {
          name: form.get('name'),
          code: form.get('code') || '',
          description: form.get('description') || null,
          color,
        }),
      )
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not create the class.')
      setBusy(false)
    }
  }

  return (
    <form onSubmit={submit} className="form-grid">
      <ErrorNote>{error}</ErrorNote>
      <label className="field span-2">
        <span>Class name</span>
        <input className="input" name="name" required maxLength={160} placeholder="Compiler Design · Slot B1" autoFocus />
      </label>
      <label className="field">
        <span>Course code <span className="hint">· optional</span></span>
        <input className="input mono" name="code" maxLength={30} placeholder="BCSE307L" />
      </label>
      <div className="field">
        <span>Colour</span>
        <div className="row" style={{ gap: 6, minHeight: 38 }}>
          {COLORS.map((c) => (
            <button
              key={c}
              type="button"
              aria-label={`Colour ${c}`}
              aria-pressed={color === c}
              onClick={() => setColor(c)}
              style={{
                width: 24,
                height: 24,
                borderRadius: 6,
                background: c,
                border: 0,
                cursor: 'pointer',
                outline: color === c ? '2px solid var(--ink)' : 'none',
                outlineOffset: 2,
              }}
            />
          ))}
        </div>
      </div>
      <label className="field span-2">
        <span>Description <span className="hint">· optional</span></span>
        <textarea className="textarea" name="description" style={{ minHeight: 70 }} maxLength={2000} />
      </label>
      <div className="span-2 row" style={{ justifyContent: 'flex-end' }}>
        <button className="btn primary" type="submit" disabled={busy}>{busy ? 'Creating…' : 'Create class'}</button>
      </div>
    </form>
  )
}

export function TeacherHome() {
  const { user } = useAuth()
  const navigate = useNavigate()
  const { data, error, loading } = useLoad<Course[]>('/api/courses')
  const [creating, setCreating] = useState(false)
  const toReview = (data ?? []).reduce((sum, c) => sum + c.open_count, 0)

  return (
    <main className="page">
      <div className="spread" style={{ alignItems: 'flex-end' }}>
        <div>
          <p className="kicker">Good to see you, {user?.name.replace(/^(dr|prof|mr|mrs|ms)\.?\s+/i, '').split(' ')[0]}</p>
          <h1 className="display" style={{ marginTop: 12 }}>
            {toReview ? <>{toReview} submission{toReview === 1 ? '' : 's'} <em>waiting</em> for you.</> : 'Your classes'}
          </h1>
        </div>
        <button className="btn primary" type="button" onClick={() => setCreating(true)}>
          <Plus size={15} /> New class
        </button>
      </div>

      <ErrorNote>{error}</ErrorNote>
      {!data && loading && <div style={{ marginTop: 24 }}><Spinner /></div>}
      {data && data.length === 0 && (
        <Empty title="No classes yet">
          Create one, then share its 6-letter code with your students so they can join.
        </Empty>
      )}
      {data && data.length > 0 && (
        <div className="classes" style={{ marginTop: 30 }}>
          {data.map((course) => <ClassCard key={course.id} course={course} href={`/classes/${course.id}`} />)}
        </div>
      )}

      <Sheet open={creating} title="New class" onClose={() => setCreating(false)}>
        <NewClass onCreated={(course) => navigate(`/classes/${course.id}`)} />
      </Sheet>
    </main>
  )
}
