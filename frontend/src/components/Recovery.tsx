import { useEffect, useState } from 'react'
import { Copy, Mail } from 'lucide-react'
import { Link } from 'react-router-dom'
import { api } from '../lib/api'
import { dueLabel, minutesLabel } from '../lib/format'
import { ErrorNote, Sheet, Spinner } from './ui'

interface Item {
  id: number
  title: string
  course: string | null
  source: string
  due_at: string | null
  minutes: number
  reason: string
}

interface Recovery {
  budget_minutes: number
  needed_minutes: number
  keep: Item[]
  ask_extension: Item[]
  defer: Item[]
  missed: Item[]
  headline: string
}

interface Draft {
  to: string | null
  subject: string
  body: string
  generated_by: 'ai' | 'template'
}

const HOURS = [3, 6, 9, 12]

function Row({ item, onClose }: { item: Item; onClose: () => void }) {
  return (
    <li>
      <Link to={`/work/${item.id}`} onClick={onClose} style={{ fontWeight: 500 }}>{item.title}</Link>
      <span className="muted tiny" style={{ display: 'block' }}>
        {[item.course, item.due_at ? `due ${dueLabel(item.due_at)}` : null, minutesLabel(item.minutes)].filter(Boolean).join(' · ')}
      </span>
      <span className="tiny" style={{ display: 'block', color: 'var(--ink-2)' }}>{item.reason}</span>
    </li>
  )
}

function ExtensionDraft({ item }: { item: Item }) {
  const [draft, setDraft] = useState<Draft | null>(null)
  const [busy, setBusy] = useState(false)
  const [copied, setCopied] = useState(false)
  const load = async () => {
    setBusy(true)
    try {
      setDraft(await api.post<Draft>(`/api/work/${item.id}/extension-draft`))
    } finally {
      setBusy(false)
    }
  }
  if (!draft) {
    return (
      <button className="btn small" type="button" onClick={load} disabled={busy} style={{ marginTop: 6 }}>
        <Mail size={13} /> {busy ? 'Drafting…' : 'Draft an extension request'}
      </button>
    )
  }
  const text = `Subject: ${draft.subject}\n\n${draft.body}`
  return (
    <div className="panel" style={{ marginTop: 8, padding: 12 }}>
      <p className="tiny muted">
        {draft.to ? `To ${draft.to} · ` : ''}Draft only. UniTask never sends it. Replace [reason] with your real reason.
        {draft.generated_by === 'ai' ? ' Written by the AI.' : ' From a template.'}
      </p>
      <p className="small" style={{ fontWeight: 600, marginTop: 8 }}>{draft.subject}</p>
      <p className="prose small" style={{ marginTop: 6 }}>{draft.body}</p>
      <button className="btn small" type="button" style={{ marginTop: 8 }} onClick={async () => { await navigator.clipboard.writeText(text); setCopied(true) }}>
        <Copy size={13} /> {copied ? 'Copied' : 'Copy'}
      </button>
    </div>
  )
}

/** "I'm behind": a realistic triage of the next few days instead of a longer to-do list. */
export function RecoverySheet({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [hours, setHours] = useState<number | null>(null)
  const [data, setData] = useState<Recovery | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!open) return
    api
      .get<Recovery>(`/api/recovery${hours ? `?hours=${hours}` : ''}`)
      .then((d) => { setData(d); setError(null) })
      .catch((e) => setError(e instanceof Error ? e.message : 'Could not build a plan.'))
  }, [open, hours])

  const keepMinutes = data ? data.keep.reduce((s, i) => s + i.minutes, 0) : 0
  const over = data ? Math.max(0, data.needed_minutes - data.budget_minutes) : 0
  const total = data ? Math.max(data.needed_minutes, data.budget_minutes, 1) : 1

  return (
    <Sheet open={open} title="Recovery plan" onClose={onClose} wide>
      <div className="stack">
        <div className="spread">
          <p className="muted small">How many hours can you really study over the next 3 days?</p>
          <div className="segmented" role="group" aria-label="Hours available">
            <button type="button" aria-pressed={hours === null} onClick={() => setHours(null)}>My usual</button>
            {HOURS.map((h) => (
              <button key={h} type="button" aria-pressed={hours === h} onClick={() => setHours(h)}>{h}h</button>
            ))}
          </div>
        </div>
        <ErrorNote>{error}</ErrorNote>
        {!data && !error && <Spinner />}
        {data && (
          <>
            <p style={{ fontSize: 17, fontWeight: 500 }}>{data.headline}</p>
            <div>
              <div className="budget-bar" aria-hidden="true">
                <span style={{ width: `${(keepMinutes / total) * 100}%`, background: 'var(--ok)' }} />
                <span style={{ width: `${(Math.max(0, data.budget_minutes - keepMinutes) / total) * 100}%`, background: 'var(--rule-strong)' }} />
                <span style={{ width: `${(over / total) * 100}%`, background: 'var(--accent)' }} />
              </div>
              <p className="tiny muted">
                Planned {minutesLabel(keepMinutes)} of the {minutesLabel(data.budget_minutes)} you have
                {over > 0 ? ` · ${minutesLabel(over)} more work than time` : ' · everything fits'}
              </p>
            </div>
            <div className="triage">
              <div className="col">
                <h3 style={{ color: 'var(--ok)' }}>Do these · {data.keep.length}</h3>
                <ul>{data.keep.length ? data.keep.map((i) => <Row key={i.id} item={i} onClose={onClose} />) : <li className="muted">Nothing urgent.</li>}</ul>
              </div>
              <div className="col">
                <h3 style={{ color: 'var(--warn)' }}>Ask for more time · {data.ask_extension.length}</h3>
                <ul>
                  {data.ask_extension.length ? data.ask_extension.map((i) => (
                    <li key={i.id}>
                      <Row item={i} onClose={onClose} />
                      <ExtensionDraft item={i} />
                    </li>
                  )) : <li className="muted">No extension needed.</li>}
                </ul>
              </div>
              <div className="col">
                <h3>Push to later · {data.defer.length}</h3>
                <ul>{data.defer.length ? data.defer.map((i) => <Row key={i.id} item={i} onClose={onClose} />) : <li className="muted">Nothing to push.</li>}</ul>
                {data.missed.length > 0 && (
                  <>
                    <h3 style={{ marginTop: 12, color: 'var(--accent)' }}>Closed · {data.missed.length}</h3>
                    <ul>{data.missed.map((i) => <Row key={i.id} item={i} onClose={onClose} />)}</ul>
                  </>
                )}
              </div>
            </div>
            <p className="tiny muted">Ranking: work left against time left, points and deadline. The plan never places work after a deadline.</p>
          </>
        )}
      </div>
    </Sheet>
  )
}
