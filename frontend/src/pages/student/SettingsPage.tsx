import { useState, type FormEvent } from 'react'
import { ErrorNote, PageHead, Spinner } from '../../components/ui'
import { api } from '../../lib/api'
import type { Profile } from '../../lib/types'
import { useAction } from '../../lib/useAction'
import { useLoad } from '../../lib/useLoad'

const LEGACY_KEY = 'unitask-demo-data-v1'

function legacyData(): { subjects: unknown[]; assignments: unknown[] } | null {
  try {
    const raw = localStorage.getItem(LEGACY_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed?.assignments) ? { subjects: parsed.subjects ?? [], assignments: parsed.assignments } : null
  } catch {
    return null
  }
}

export function SettingsPage() {
  const { data, setData, error } = useLoad<Profile>('/api/profile')
  const save = useAction()
  const data2 = useAction()
  const [saved, setSaved] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const legacy = legacyData()

  if (!data) return <main className="page narrow">{error ? <ErrorNote>{error}</ErrorNote> : <Spinner />}</main>

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const f = new FormData(event.currentTarget)
    save.run(async () => {
      setData(
        await api.patch<Profile>('/api/profile', {
          name: f.get('name'),
          university: f.get('university') || null,
          semester: f.get('semester') || null,
          timezone: f.get('timezone'),
          day_start: f.get('day_start'),
          day_end: f.get('day_end'),
          daily_study_minutes: Number(f.get('daily_study_minutes')),
          pace: f.get('pace'),
          explain_style: f.get('explain_style'),
          background: f.get('background') || null,
          attendance_threshold: f.get('attendance_threshold') ? Number(f.get('attendance_threshold')) : null,
          onboarded: true,
        }),
      )
      setSaved(true)
      window.setTimeout(() => setSaved(false), 2500)
    })
  }

  const importLegacy = () =>
    data2.run(async () => {
      const result = await api.post<{ created: number; merged: number; unchanged: number }>('/api/import/legacy', legacy)
      setMessage(`Imported from the earlier version: ${result.created} new, ${result.merged} merged, ${result.unchanged} already here.`)
    })
  const removeDemo = () =>
    data2.run(async () => {
      if (!window.confirm('Remove the demo subject with its files, deadlines and exam?')) return
      await api.del('/api/demo')
      setMessage('Demo subject removed.')
    })
  const addDemo = () =>
    data2.run(async () => {
      await api.post('/api/demo')
      setMessage('Demo subject added. Look for “Demo · Data Structures”.')
    })
  const zones = (Intl as unknown as { supportedValuesOf?: (k: string) => string[] }).supportedValuesOf?.('timeZone') ?? [data.timezone]

  return (
    <main className="page narrow">
      <PageHead kicker={data.user.email} title="Settings" />
      <form className="stack" style={{ gap: 20 }} onSubmit={submit}>
        <section className="panel form-grid">
          <h3 className="span-2">You</h3>
          <label className="field span-2"><span>Name</span><input className="input" name="name" defaultValue={data.user.name} required maxLength={120} /></label>
          <label className="field"><span>University</span><input className="input" name="university" defaultValue={data.university ?? ''} maxLength={160} /></label>
          <label className="field"><span>Semester</span><input className="input" name="semester" defaultValue={data.semester ?? ''} maxLength={60} /></label>
          <label className="field span-2"><span>Time zone</span>
            <select className="select" name="timezone" defaultValue={data.timezone}>{zones.map((z) => <option key={z} value={z}>{z}</option>)}</select>
          </label>
        </section>

        <section className="panel form-grid">
          <h3 className="span-2">When you study</h3>
          <p className="muted small span-2">The planner only places study inside this window, around your classes, up to the daily limit.</p>
          <label className="field"><span>Day starts</span><input className="input" type="time" name="day_start" defaultValue={data.day_start} required /></label>
          <label className="field"><span>Day ends</span><input className="input" type="time" name="day_end" defaultValue={data.day_end} required /></label>
          <label className="field span-2"><span>Most study in one day (minutes)</span><input className="input" type="number" name="daily_study_minutes" min={30} max={960} step={15} defaultValue={data.daily_study_minutes} /></label>
          <label className="field span-2"><span>Minimum attendance your university requires (%)</span><input className="input" type="number" name="attendance_threshold" min={1} max={100} defaultValue={data.attendance_threshold ?? ''} placeholder="e.g. 75" /></label>
        </section>

        <section className="panel form-grid">
          <h3 className="span-2">How you learn</h3>
          <p className="muted small span-2">The tutor reads this every time it explains something to you.</p>
          <label className="field"><span>Pace</span>
            <select className="select" name="pace" defaultValue={data.pace}><option value="slow">Slow · one idea at a time</option><option value="steady">Steady</option><option value="fast">Fast · skip what I know</option></select>
          </label>
          <label className="field"><span>Explanations</span>
            <select className="select" name="explain_style" defaultValue={data.explain_style}>
              <option value="examples">Worked examples first</option>
              <option value="step_by_step">Step by step</option>
              <option value="analogies">Everyday analogies</option>
              <option value="concise">Short and precise</option>
            </select>
          </label>
          <label className="field span-2"><span>Your background, in your own words</span>
            <textarea className="textarea" name="background" rows={3} defaultValue={data.background ?? ''} maxLength={2000} placeholder="Comfortable with C; maths proofs make me nervous; I understand diagrams better than formulas." />
          </label>
        </section>

        <ErrorNote>{save.error}</ErrorNote>
        <div className="row" style={{ gap: 10 }}>
          <button className="btn primary" type="submit" disabled={save.busy}>{save.busy ? 'Saving…' : 'Save settings'}</button>
          {saved && <span className="pill ok">Saved</span>}
        </div>
      </form>

      <section className="panel stack" style={{ marginTop: 28 }}>
        <h3>AI and services on this server</h3>
        <p className="small">
          Model: <strong>{data.ai.available ? `${data.ai.provider} · ${data.ai.model}` : 'none configured'}</strong>
          {data.ai.fallback && ` (falls back to ${data.ai.fallback})`} · OCR: <strong>{data.ai.ocr}</strong> · Email reminders: <strong>{data.ai.email === 'ses' ? 'Amazon SES' : 'in-app only'}</strong>
        </p>
      </section>

      <section className="panel stack" style={{ marginTop: 16 }}>
        <h3>Your data</h3>
        <ErrorNote>{data2.error}</ErrorNote>
        {message && <div className="note ok">{message}</div>}
        {legacy ? (
          <div className="spread">
            <span className="small">This browser has {legacy.assignments.length} assignments saved by the earlier version of UniTask.</span>
            <button className="btn small" type="button" onClick={importLegacy} disabled={data2.busy}>Import them</button>
          </div>
        ) : <p className="muted small">No data from the earlier version of UniTask was found in this browser.</p>}
        <div className="row" style={{ gap: 8 }}>
          <button className="btn small" type="button" onClick={addDemo} disabled={data2.busy}>Add the demo subject</button>
          <button className="btn small ghost danger" type="button" onClick={removeDemo} disabled={data2.busy}>Remove the demo subject</button>
        </div>
      </section>
    </main>
  )
}
