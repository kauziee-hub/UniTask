import { useEffect, useMemo, useRef, useState } from 'react'
import { ArrowRight, BookOpen, CalendarDays, Edit3, FileUp, ImagePlus, Plus, Send, Sparkles, Trash2, Unplug } from 'lucide-react'
import type { CSSProperties } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useAppData } from '../data/useAppData'
import { daysUntilDue, formatDueDate, type Assignment, type AssignmentStatus, type Subject } from '../data/sampleData'
import { FeedbackState } from '../components/FeedbackState'
import { AssignmentEditor } from '../components/AssignmentEditor'
import { SubjectEditor } from '../components/SubjectEditor'

type WorkspacePageName = 'assignments' | 'calendar' | 'subjects' | 'assistant' | 'integrations' | 'settings' | 'timetable' | 'not-found'

interface WorkspacePageProps {
  page: WorkspacePageName
}

const headings: Record<WorkspacePageName, { title: string; subtitle: string }> = {
  assignments: { title: 'Assignments', subtitle: 'A single view of the work ahead across your subjects.' },
  calendar: { title: 'Calendar', subtitle: 'See your academic deadlines at a glance.' },
  subjects: { title: 'Subjects', subtitle: 'Your current semester, organized by course.' },
  assistant: { title: 'AI Assistant', subtitle: 'Ask about tasks, priorities, and a manageable plan.' },
  integrations: { title: 'Integrations', subtitle: 'Understand where your assignment information comes from.' },
  settings: { title: 'Settings', subtitle: 'Manage your academic workspace preferences.' },
  timetable: { title: 'Timetable & import', subtitle: 'Preview a timetable image or import assignments from a CSV/JSON file.' },
  'not-found': { title: 'Page not found', subtitle: 'The page you requested does not exist.' },
}

const weekdays = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

function isValidDueDate(value: string) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false
  const date = new Date(`${value}T00:00:00`)
  const [year, month, day] = value.split('-').map(Number)
  return date.getFullYear() === year && date.getMonth() + 1 === month && date.getDate() === day
}
function AssistantPanel({ assignments, subjects }: { assignments: Assignment[]; subjects: Subject[] }) {
  const [prompt, setPrompt] = useState('')
  const [messages, setMessages] = useState<{ role: 'user' | 'assistant'; text: string }[]>([
    { role: 'assistant', text: 'I can answer questions using the assignments and subjects saved in this browser. Try asking what is due this week or request a short study plan.' },
  ])

  const answer = (question: string) => {
    const query = question.toLowerCase()
    let relevant = assignments.filter((item) => item.status !== 'Completed')
    const subjectQuery = subjects.find((subject) => query.includes(subject.name.toLowerCase()) || query.includes(subject.code.toLowerCase()))
    if (subjectQuery) relevant = relevant.filter((item) => item.subjectId === subjectQuery.id)
    if (query.includes('today')) relevant = relevant.filter((item) => daysUntilDue(item.dueDate) === 0)
    else if (query.includes('week') || query.includes('friday')) relevant = relevant.filter((item) => {
      const days = daysUntilDue(item.dueDate)
      return days >= 0 && days <= 7
    })

    relevant.sort((left, right) => daysUntilDue(left.dueDate) - daysUntilDue(right.dueDate))
    if (relevant.length === 0) return 'No pending assignments match that request. Your saved assignment data is up to date.'

    const requestedHours = Number(query.match(/(\d+(?:\.\d+)?)\s*(?:hours?|hrs?)/)?.[1])
    const isPlan = query.includes('plan') || query.includes('hours') || query.includes('prioriti') || query.includes('important')
    const selected = requestedHours ? relevant.slice(0, Math.max(1, Math.floor(requestedHours))) : relevant.slice(0, 6)
    const lines = selected.map((item, index) => {
      const subject = subjects.find((entry) => entry.id === item.subjectId)
      const due = daysUntilDue(item.dueDate)
      const dueText = due < 0 ? `overdue by ${Math.abs(due)} day(s)` : due === 0 ? 'due today' : `due ${formatDueDate(item.dueDate)}`
      return `${index + 1}. ${item.title} (${subject?.code ?? 'No subject'}) — ${dueText}${isPlan ? `; suggested focus ${requestedHours ? `${Math.max(1, Math.floor(requestedHours / selected.length))}h` : '1h'}` : ''}`
    })
    if (isPlan) return `Deterministic study suggestion, ranked by deadline${subjectQuery ? ` for ${subjectQuery.name}` : ''}:\n${lines.join('\n')}\n\nTime estimates are suggestions, not measured workload. Adjust them to fit your schedule.`
    return `${relevant.length} pending task(s)${subjectQuery ? ` for ${subjectQuery.name}` : ''}, sorted by deadline:\n${lines.join('\n')}`
  }

  const sendMessage = (text = prompt) => {
    const question = text.trim()
    if (!question) return
    setMessages((current) => [...current, { role: 'user', text: question }, { role: 'assistant', text: answer(question) }])
    setPrompt('')
  }

  return (
    <section className="panel page-panel">
      <div className="section-heading"><div><h2 className="section-title">Assignment assistant</h2><div className="section-note">Deterministic answers from your local saved assignments · no LLM/API is configured.</div></div><Sparkles size={17} color="var(--primary)" /></div>
      <div className="suggested-prompts">
        {['What is due today?', 'Prioritize my work this week', 'Make a 3 hour study plan'].map((item) => <button className="action-button" type="button" key={item} onClick={() => sendMessage(item)}>{item}</button>)}
      </div>
      <div className="chat-history" aria-live="polite">
        {messages.map((message, index) => <div className={`chat-bubble${message.role === 'user' ? ' user' : ''}`} key={`${index}-${message.role}`}>{message.text}</div>)}
      </div>
      <form className="chat-composer" onSubmit={(event) => { event.preventDefault(); sendMessage() }}>
        <textarea aria-label="Ask about your assignments" placeholder="Ask about deadlines, subjects, priorities, or a study plan..." value={prompt} onChange={(event) => setPrompt(event.target.value)} />
        <button className="primary-button" type="submit" aria-label="Send message"><Send size={15} /></button>
      </form>
    </section>
  )
}

function parseCsv(text: string, subjects: Subject[]): Omit<Assignment, 'id'>[] {
  const rows = text.trim().split(/\r?\n/)
  if (rows.length < 2) throw new Error('CSV needs a header and at least one assignment row.')
  const split = (line: string) => {
    const cells: string[] = []
    const expression = /(?:^|,)(?:"((?:[^"]|"")*)"|([^,]*))/g
    let match: RegExpExecArray | null
    while ((match = expression.exec(line)) !== null) cells.push((match[1] ?? match[2] ?? '').replaceAll('""', '"').trim())
    return cells
  }
  const headers = split(rows[0]).map((header) => header.toLowerCase())
  const titleIndex = headers.indexOf('title')
  const subjectIndex = headers.indexOf('subjectcode')
  const dueIndex = headers.indexOf('duedate')
  if ([titleIndex, subjectIndex, dueIndex].some((index) => index < 0)) {
    throw new Error('CSV headers must include title, subjectCode, and dueDate.')
  }
  return rows.slice(1).filter((row) => row.trim()).map((row, index) => {
    const cells = split(row)
    const title = cells[titleIndex]
    const subjectCode = cells[subjectIndex]?.toUpperCase()
    const dueDate = cells[dueIndex]
    const subject = subjects.find((item) => item.code.toUpperCase() === subjectCode)
    if (!title || !subject || !isValidDueDate(dueDate ?? '')) {
      throw new Error(`Invalid assignment data on CSV row ${index + 2}; check title, existing subjectCode, and YYYY-MM-DD dueDate.`)
    }
    return { title, subjectId: subject.id, dueDate, status: 'Not started' as AssignmentStatus, platform: cells[headers.indexOf('platform')] || 'CSV import' }
  })
}

function ImportPanel() {
  const { subjects, importAssignments } = useAppData()
  const [message, setMessage] = useState('')
  const [previewUrl, setPreviewUrl] = useState('')
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState('')
  const [uploadedImages, setUploadedImages] = useState<{ id: string; original_filename: string; file_url: string; storage_provider: string }[]>([])
  const fileRef = useRef<HTMLInputElement>(null)

  const refreshUploads = async () => {
    try {
      const response = await fetch('/api/timetables')
      if (!response.ok) throw new Error(`Timetable list request failed (${response.status}).`)
      setUploadedImages(await response.json())
      setUploadError('')
    } catch (error) {
      setUploadError(error instanceof Error ? error.message : 'Could not load stored timetable images.')
    }
  }

  useEffect(() => {
    let active = true
    fetch('/api/timetables')
      .then(async (response) => {
        if (!response.ok) throw new Error(`Timetable list request failed (${response.status}).`)
        return response.json()
      })
      .then((images) => {
        if (active) setUploadedImages(images)
      })
      .catch((error: unknown) => {
        if (active) setUploadError(error instanceof Error ? error.message : 'Could not load stored timetable images.')
      })
    return () => {
      active = false
    }
  }, [])

  useEffect(() => () => {
    if (previewUrl) URL.revokeObjectURL(previewUrl)
  }, [previewUrl])

  const importFile = async (file?: File) => {
    if (!file) return
    setMessage('')
    if (file.size > 2_000_000) {
      setMessage('File is larger than 2 MB. Choose a smaller CSV or JSON file.')
      return
    }
    try {
      const text = await file.text()
      let rows: Omit<Assignment, 'id'>[]
      if (file.name.toLowerCase().endsWith('.json')) {
        const data = JSON.parse(text) as unknown
        if (!Array.isArray(data)) throw new Error('JSON file must contain an array of assignments.')
        rows = data.map((row, index) => {
          if (!row || typeof row !== 'object') throw new Error(`Invalid JSON assignment at item ${index + 1}.`)
          const item = row as Record<string, unknown>
          const subject = subjects.find((entry) => entry.code.toUpperCase() === String(item.subjectCode ?? '').toUpperCase())
          if (typeof item.title !== 'string' || !subject || typeof item.dueDate !== 'string' || !isValidDueDate(item.dueDate)) {
            throw new Error(`Each JSON item needs title, an existing subjectCode, and dueDate in YYYY-MM-DD format (item ${index + 1}).`)
          }
          return { title: item.title.trim(), subjectId: subject.id, dueDate: item.dueDate, status: 'Not started', platform: typeof item.platform === 'string' ? item.platform : 'JSON import' }
        })
      } else if (file.name.toLowerCase().endsWith('.csv')) {
        rows = parseCsv(text, subjects)
      } else {
        throw new Error('Choose a .csv or .json assignment file.')
      }
      if (rows.length === 0) throw new Error('No assignments were found in the import file.')
      const count = importAssignments(rows)
      setMessage(`Imported ${count} assignment(s) into this browser.`)
      if (fileRef.current) fileRef.current.value = ''
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Could not import this file.')
    }
  }

  const previewImage = (file?: File) => {
    if (previewUrl) URL.revokeObjectURL(previewUrl)
    setPreviewUrl('')
    if (!file) return
    if (!file.type.startsWith('image/')) {
      setMessage('Choose an image file for timetable preview.')
      return
    }
    if (file.size > 5_000_000) {
      setMessage('Image is larger than 5 MB.')
      return
    }
    setPreviewUrl(URL.createObjectURL(file))
    setMessage('Image preview only. No OCR or timetable extraction is implemented.')
    setUploadError('')
  }

  const uploadImage = async (file?: File) => {
    if (!file) return
    setUploadError('')
    if (file.size > 5 * 1024 * 1024) {
      setUploadError('Image exceeds the 5 MB upload limit.')
      return
    }
    const body = new FormData()
    body.append('file', file)
    setUploading(true)
    setMessage('')
    try {
      const response = await fetch('/api/timetables', { method: 'POST', body })
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail ?? `Upload failed (${response.status}).`)
      setMessage(`Uploaded ${data.original_filename} to ${data.storage_provider === 's3' ? 'private S3 storage' : 'local backend storage'}.`)
      await refreshUploads()
    } catch (error) {
      setUploadError(error instanceof Error ? error.message : 'Timetable upload failed.')
    } finally {
      setUploading(false)
    }
  }

  return (
    <div className="left-stack">
      <section className="panel">
        <div className="section-heading"><div><h2 className="section-title">Import assignments</h2><div className="section-note">CSV headers: title, subjectCode, dueDate, platform</div></div><FileUp size={17} color="var(--primary)" /></div>
        <div className="import-dropzone">
          <FileUp size={22} color="var(--primary)" />
          <strong>Choose an assignment file</strong>
          <span>CSV or JSON · saved to local browser storage</span>
          <input ref={fileRef} type="file" accept=".csv,.json,text/csv,application/json" aria-label="Import assignment CSV or JSON" onChange={(event) => void importFile(event.target.files?.[0])} />
        </div>
        <p className="section-note" style={{ marginTop: 10 }}>Subject codes must match an existing subject. Example CSV: <code>title,subjectCode,dueDate,platform</code>.</p>
      </section>
      <section className="panel">
        <div className="section-heading"><div><h2 className="section-title">Timetable image</h2><div className="section-note">Uploads go to the configured backend storage. OCR is not available.</div></div><ImagePlus size={17} color="var(--primary)" /></div>
        <label className="import-dropzone">
          <ImagePlus size={22} color="var(--primary)" />
          <strong>{uploading ? 'Uploading timetable…' : 'Choose and upload timetable image'}</strong>
          <span>JPEG, PNG, or WebP · maximum 5 MB · private backend storage</span>
          <input type="file" accept="image/jpeg,image/png,image/webp,.jpg,.jpeg,.png,.webp" aria-label="Choose timetable image" disabled={uploading} onChange={(event) => { const file = event.target.files?.[0]; previewImage(file); void uploadImage(file) }} />
        </label>
        {previewUrl && <img src={previewUrl} alt="Selected timetable preview" style={{ display: 'block', maxWidth: '100%', maxHeight: 280, margin: '14px auto 0', borderRadius: 8 }} />}
        {uploading && <div className="section-note" role="status" style={{ marginTop: 10 }}>Uploading to the backend. Please keep this page open.</div>}
        {uploadError && <div className="auth-note" role="alert">{uploadError} Ensure the backend is running.</div>}
        {uploadedImages.length > 0 && <div className="uploaded-images"><h3 className="section-title">Uploaded timetables</h3>{uploadedImages.map((image) => <figure key={image.id} className="uploaded-image"><img src={image.file_url} alt={`Uploaded timetable: ${image.original_filename}`} /><figcaption>{image.original_filename} · {image.storage_provider}</figcaption></figure>)}</div>}
      </section>
      {message && <div className="auth-note" role="status">{message}</div>}
    </div>
  )
}

export function WorkspacePage({ page }: WorkspacePageProps) {
  const { assignments, subjects, deleteAssignment, completeAssignment, deleteSubject, resetDemoData } = useAppData()
  const { title, subtitle } = headings[page]
  const [searchParams] = useSearchParams()
  const assignmentSearch = searchParams.get('search')?.toLowerCase().trim() ?? ''
  const [assignmentEdit, setAssignmentEdit] = useState<Assignment | null>(null)
  const [addingAssignment, setAddingAssignment] = useState(false)
  const [subjectEdit, setSubjectEdit] = useState<Subject | null>(null)
  const [addingSubject, setAddingSubject] = useState(false)
  const matchingAssignments = useMemo(() => assignments.filter((assignment) => {
    const subject = subjects.find((item) => item.id === assignment.subjectId)
    return `${assignment.title} ${subject?.name ?? ''} ${assignment.platform}`.toLowerCase().includes(assignmentSearch)
  }).toSorted((left, right) => left.dueDate.localeCompare(right.dueDate)), [assignments, assignmentSearch, subjects])
  const days = weekdays.map((day, index) => {
    const date = new Date()
    const mondayOffset = (date.getDay() + 6) % 7
    date.setDate(date.getDate() - mondayOffset + index)
    return { day, date, today: date.toDateString() === new Date().toDateString() }
  })

  const addAssignment = () => {
    if (subjects.length === 0) {
      window.alert('Add a subject before creating an assignment.')
      return
    }
    setAddingAssignment(true)
  }

  const confirmDeleteSubject = (subject: Subject) => {
    const linkedCount = assignments.filter((assignment) => assignment.subjectId === subject.id).length
    const confirmation = linkedCount
      ? `Delete ${subject.name} and its ${linkedCount} linked assignment(s)?`
      : `Delete ${subject.name}?`
    if (window.confirm(confirmation)) deleteSubject(subject.id)
  }

  return (
    <div className="content">
      <div className="page-heading">
        <div><div className="eyebrow">Fall semester · 2026</div><h1 className="page-title">{title}</h1><div className="page-subtitle">{subtitle}</div></div>
        {page === 'assignments' && <button className="primary-button" type="button" onClick={addAssignment}><Plus size={14} /> Add assignment</button>}
        {page === 'subjects' && <button className="primary-button" type="button" onClick={() => setAddingSubject(true)}><Plus size={14} /> Add subject</button>}
      </div>

      {page === 'assignments' && (
        <section className="panel page-panel">
          <div className="section-heading"><div><h2 className="section-title">All assignments</h2><div className="section-note">Persisted in this browser only · mark complete, edit, or delete.</div></div><span className="status-pill in-progress">{matchingAssignments.length} shown</span></div>
          <div className="simple-list">
            {matchingAssignments.map((assignment) => {
              const subject = subjects.find((item) => item.id === assignment.subjectId)
              const daysLeft = daysUntilDue(assignment.dueDate)
              return (
                <div className="simple-row" key={assignment.id}>
                  <span style={{ color: 'var(--ink)', fontWeight: 600, flex: 1 }}>{assignment.title}<span className="subject-caption" style={{ display: 'block' }}>{subject?.name ?? 'Unassigned'} · {assignment.platform}</span></span>
                  <span className={`status-pill${assignment.status === 'In progress' ? ' in-progress' : assignment.status === 'Completed' ? ' complete' : ''}`}>{assignment.status}</span>
                  <span className={daysLeft < 0 && assignment.status !== 'Completed' ? 'due-label urgent' : 'due-label'}>{assignment.status === 'Completed' ? 'Complete' : daysLeft < 0 ? `Overdue ${Math.abs(daysLeft)}d` : formatDueDate(assignment.dueDate)}</span>
                  <div className="row-actions">
                    <button className="action-button" type="button" onClick={() => completeAssignment(assignment.id)}>{assignment.status === 'Completed' ? 'Reopen' : 'Complete'}</button>
                    <button className="icon-button" type="button" aria-label={`Edit ${assignment.title}`} onClick={() => setAssignmentEdit(assignment)}><Edit3 size={14} /></button>
                    <button className="icon-button" type="button" aria-label={`Delete ${assignment.title}`} onClick={() => { if (window.confirm(`Delete “${assignment.title}”?`)) deleteAssignment(assignment.id) }}><Trash2 size={14} /></button>
                  </div>
                </div>
              )
            })}
            {matchingAssignments.length === 0 && <FeedbackState kind="empty" title="No matching assignments" description={assignmentSearch ? `No assignments match “${searchParams.get('search')}”.` : 'Add an assignment to get started.'} />}
          </div>
        </section>
      )}

      {page === 'calendar' && (
        <section className="panel">
          <div className="section-heading"><div><h2 className="section-title">This week</h2><div className="section-note">Live from your saved assignment due dates.</div></div><CalendarDays size={17} color="var(--primary)" /></div>
          <div className="calendar-grid">
            {days.map(({ day, date, today }) => {
              const midnightToday = new Date()
              midnightToday.setHours(0, 0, 0, 0)
              const daysFromToday = Math.round((date.getTime() - midnightToday.getTime()) / 86_400_000)
              const due = assignments.filter((assignment) => daysUntilDue(assignment.dueDate) === daysFromToday)
              return <article className={`calendar-day${today ? ' today' : ''}`} key={day}><div className="calendar-day-name">{day}</div><div className="calendar-day-number">{date.getDate()}</div>{due.map((assignment) => <div className={`calendar-event${assignment.status === 'Completed' ? ' complete' : ''}`} key={assignment.id}>{assignment.title}{assignment.status === 'Completed' ? ' · done' : ''}</div>)}</article>
            })}
          </div>
        </section>
      )}

      {page === 'subjects' && (
        <>
          <section className="metric-grid">
            {subjects.map((subject) => {
              const linked = assignments.filter((assignment) => assignment.subjectId === subject.id)
              const pending = linked.filter((assignment) => assignment.status !== 'Completed').length
              return <article className="panel" key={subject.id}><span className="subject-dot" style={{ display: 'block', '--dot-color': subject.color } as CSSProperties} /><div className="section-title" style={{ marginTop: 12 }}>{subject.name}</div><div className="section-note">{subject.code}</div><div className="simple-row" style={{ marginTop: 16 }}>Pending <strong>{pending}</strong></div><div className="simple-row">Completed <strong>{linked.length - pending}</strong></div><div className="subject-actions" style={{ marginTop: 12 }}><button className="action-button" type="button" onClick={() => setSubjectEdit(subject)}>Edit</button><button className="action-button danger" type="button" onClick={() => confirmDeleteSubject(subject)}>Delete</button></div></article>
            })}
          </section>
          {subjects.length === 0 && <section className="panel"><FeedbackState kind="empty" title="No subjects yet" description="Add a subject before creating assignments." /></section>}
        </>
      )}

      {page === 'assistant' && <AssistantPanel assignments={assignments} subjects={subjects} />}

      {page === 'timetable' && <ImportPanel />}

      {page === 'integrations' && (
        <section className="panel page-panel">
          <div className="section-heading"><div><h2 className="section-title">Platform status</h2><div className="section-note">No live LMS integrations are configured in this demo.</div></div><Unplug size={17} color="var(--primary)" /></div>
          <div className="simple-list">
            {['Moodle', 'Google Classroom'].map((platform) => <div className="simple-row" key={platform}><span>{platform}</span><span className="status-pill">Not connected</span></div>)}
          </div>
          <div className="simple-row"><span>Manual entry and local file import</span><span className="status-pill complete">Available</span></div>
          <p className="section-note" style={{ marginTop: 14 }}>External platforms are not being accessed. Add assignments manually or import an authorized CSV/JSON export.</p>
          <Link className="secondary-button" style={{ marginTop: 14 }} to="/timetable"><FileUp size={14} /> Open timetable & import</Link>
        </section>
      )}

      {page === 'settings' && (
        <section className="panel page-panel">
          <div className="empty-state"><BookOpen size={23} color="var(--primary)" /><h2 className="section-title" style={{ marginTop: 10 }}>Local demo workspace</h2><p>Your assignments and subjects are saved in this browser&apos;s localStorage. There is no login or shared account.</p><button className="secondary-button" type="button" style={{ marginTop: 12 }} onClick={() => { if (window.confirm('Reset all local demo changes to the original sample data?')) resetDemoData() }}>Reset demo data</button></div>
        </section>
      )}

      {page === 'not-found' && <section className="panel page-panel"><FeedbackState kind="error" title="Page not found" description="The page you requested does not exist." /><Link className="text-link" to="/">Go to dashboard <ArrowRight size={13} /></Link></section>}

      {addingAssignment && <AssignmentEditor onClose={() => setAddingAssignment(false)} />}
      {assignmentEdit && <AssignmentEditor assignment={assignmentEdit} onClose={() => setAssignmentEdit(null)} />}
      {addingSubject && <SubjectEditor onClose={() => setAddingSubject(false)} />}
      {subjectEdit && <SubjectEditor subject={subjectEdit} onClose={() => setSubjectEdit(null)} />}
    </div>
  )
}
