import { useState, type FormEvent } from 'react'
import { useAppData } from '../data/useAppData'
import type { Subject } from '../data/sampleData'

const colors = ['#4f46e5', '#0d9488', '#f59e0b', '#ec4899', '#2563eb', '#8b5cf6']

export function SubjectEditor({ subject, onClose }: { subject?: Subject; onClose: () => void }) {
  const { saveSubject, subjects } = useAppData()
  const [error, setError] = useState('')

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const formData = new FormData(event.currentTarget)
    const code = String(formData.get('code')).trim().toUpperCase()
    if (subjects.some((item) => item.code.toUpperCase() === code && item.id !== subject?.id)) {
      setError('That course code is already in use.')
      return
    }
    saveSubject({
      name: String(formData.get('name')).trim(),
      code,
      color: String(formData.get('color')),
    }, subject?.id)
    onClose()
  }

  return (
    <div className="dialog-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose() }}>
      <section className="dialog" role="dialog" aria-modal="true" aria-labelledby="subject-dialog-title">
        <div className="section-heading">
          <h2 id="subject-dialog-title" className="section-title">{subject ? 'Edit subject' : 'Add subject'}</h2>
          <button type="button" className="icon-button" aria-label="Close" onClick={onClose}>×</button>
        </div>
        <form onSubmit={handleSubmit}>
          <label className="form-field"><span>Subject name</span><input name="name" required maxLength={100} defaultValue={subject?.name} autoFocus /></label>
          <label className="form-field"><span>Course code</span><input name="code" required maxLength={20} defaultValue={subject?.code} /></label>
          <label className="form-field"><span>Color</span><select name="color" defaultValue={subject?.color ?? colors[0]}>{colors.map((color) => <option value={color} key={color}>{color}</option>)}</select></label>
          {error && <div className="auth-note" role="alert">{error}</div>}
          <div className="dialog-actions"><button type="button" className="secondary-button" onClick={onClose}>Cancel</button><button className="primary-button" type="submit">Save subject</button></div>
        </form>
      </section>
    </div>
  )
}
