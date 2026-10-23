import { useState, type FormEvent } from 'react'
import { useAppData } from '../data/useAppData'
import { formatDateInput, type Assignment, type AssignmentStatus } from '../data/sampleData'

interface AssignmentEditorProps {
  assignment?: Assignment
  onClose: () => void
}

export function AssignmentEditor({ assignment, onClose }: AssignmentEditorProps) {
  const { subjects, saveAssignment } = useAppData()
  const [error, setError] = useState('')

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const formData = new FormData(event.currentTarget)
    const subjectId = String(formData.get('subjectId'))
    if (!subjects.some((subject) => subject.id === subjectId)) {
      setError('Choose an existing subject before saving.')
      return
    }
    const status = String(formData.get('status')) as AssignmentStatus
    saveAssignment({
      title: String(formData.get('title')).trim(),
      subjectId,
      dueDate: String(formData.get('dueDate')),
      status,
      platform: String(formData.get('platform')).trim() || 'Manual entry',
    }, assignment?.id)
    onClose()
  }

  return (
    <div className="dialog-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose() }}>
      <section className="dialog" role="dialog" aria-modal="true" aria-labelledby="assignment-dialog-title">
        <div className="section-heading">
          <h2 id="assignment-dialog-title" className="section-title">{assignment ? 'Edit assignment' : 'Add assignment'}</h2>
          <button type="button" className="icon-button" aria-label="Close" onClick={onClose}>×</button>
        </div>
        <form onSubmit={handleSubmit}>
          <label className="form-field"><span>Assignment title</span><input name="title" required maxLength={120} defaultValue={assignment?.title} autoFocus /></label>
          <label className="form-field"><span>Subject</span><select name="subjectId" required defaultValue={assignment?.subjectId ?? subjects[0]?.id}><option value="" disabled>Select a subject</option>{subjects.map((subject) => <option value={subject.id} key={subject.id}>{subject.code} — {subject.name}</option>)}</select></label>
          <label className="form-field"><span>Due date</span><input name="dueDate" type="date" required defaultValue={assignment?.dueDate ?? formatDateInput(new Date())} /></label>
          <label className="form-field"><span>Status</span><select name="status" defaultValue={assignment?.status ?? 'Not started'}><option>Not started</option><option>In progress</option><option>Completed</option></select></label>
          <label className="form-field"><span>Source / platform</span><input name="platform" maxLength={80} defaultValue={assignment?.platform ?? 'Manual entry'} /></label>
          {error && <div className="auth-note" role="alert">{error}</div>}
          <div className="dialog-actions"><button type="button" className="secondary-button" onClick={onClose}>Cancel</button><button className="primary-button" type="submit">Save assignment</button></div>
        </form>
      </section>
    </div>
  )
}
