import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { ErrorNote } from '../../components/ui'
import { api, type WorkItem } from '../../lib/api'
import { dueLabel, relative } from '../../lib/format'
import { useAction } from '../../lib/useAction'
import { useLoad } from '../../lib/useLoad'

interface ConnectionInfo {
  provider: string
  status: string
  account: string | null
  last_synced_at: string | null
  last_error: string | null
  last_result: Record<string, number> | null
}

function counts(result: Record<string, number> | null) {
  if (!result) return ''
  return Object.entries(result).filter(([, v]) => typeof v === 'number' && v > 0).map(([k, v]) => `${v} ${k.replace('_', ' ')}`).join(', ') || 'no changes'
}

export function MoreConnections() {
  const { data, reload } = useLoad<{ connections: Record<string, ConnectionInfo>; extension_token: boolean }>('/api/connections')
  const moodle = data?.connections.moodle_ics
  const vtop = data?.connections.vtop
  const feed = useAction()
  const file = useAction()
  const capture = useAction()
  const ext = useAction()
  const [fileResult, setFileResult] = useState<string | null>(null)
  const [captured, setCaptured] = useState<{ items: WorkItem[]; message: string } | null>(null)
  const [token, setToken] = useState<string | null>(null)

  const connectFeed = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    const url = String(new FormData(e.currentTarget).get('url'))
    feed.run(async () => { await api.post('/api/connections/moodle', { url }); await reload() })
  }
  const importFile = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    const form = e.currentTarget
    file.run(async () => {
      const r = await api.post<{ created: number; merged: number; updated: number; unchanged: number; skipped: string[] }>('/api/import/file', new FormData(form))
      setFileResult(`${r.created} added, ${r.merged} matched to items you already had, ${r.updated} updated, ${r.unchanged} unchanged.${r.skipped.length ? ` Skipped: ${r.skipped.join('; ')}` : ''}`)
      form.reset()
    })
  }
  const doCapture = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    const form = e.currentTarget
    const text = String(new FormData(form).get('text'))
    capture.run(async () => { setCaptured(await api.post('/api/capture', { text })); form.reset() })
  }

  return (
    <div className="stack" style={{ gap: 18, marginTop: 34 }}>
      <div className="section-head" style={{ marginTop: 0 }}><h2>Other ways to bring in deadlines</h2></div>

      <section className="panel stack">
        <div className="spread">
          <h3>Moodle calendar feed</h3>
          {moodle && <span className={`pill ${moodle.status === 'connected' ? 'ok' : 'accent'}`}>{moodle.status === 'connected' ? `Synced ${moodle.last_synced_at ? relative(moodle.last_synced_at) : ''}` : 'Needs attention'}</span>}
        </div>
        <p className="muted small">In Moodle: Calendar → Export calendar → “All courses”, “Recent and next 60 days” → Get calendar URL. Paste it here. UniTask re-reads it on a schedule, tracks moved deadlines and merges items it already knows from other sources.</p>
        {moodle ? (
          <>
            <p className="small">From <strong>{moodle.account}</strong> · last result: {counts(moodle.last_result)}</p>
            {moodle.last_error && <div className="note error">{moodle.last_error}</div>}
            <div className="row" style={{ gap: 8 }}>
              <button className="btn small" type="button" disabled={feed.busy} onClick={() => feed.run(async () => { await api.post('/api/connections/moodle/sync'); await reload() })}>Check now</button>
              <button className="btn small ghost danger" type="button" onClick={() => feed.run(async () => { await api.del('/api/connections/moodle'); await reload() })}>Disconnect</button>
            </div>
          </>
        ) : (
          <form className="row" style={{ gap: 8 }} onSubmit={connectFeed}>
            <input className="input" name="url" type="url" required placeholder="https://moodle.your-university.edu/calendar/export_execute.php?…" style={{ flex: 1 }} />
            <button className="btn primary" type="submit" disabled={feed.busy}>{feed.busy ? 'Reading…' : 'Connect'}</button>
          </form>
        )}
        <ErrorNote>{feed.error}</ErrorNote>
      </section>

      <section className="panel stack">
        <h3>Paste an announcement</h3>
        <p className="muted small">Paste a message or email from a teacher. Deadlines read from it are added but marked unconfirmed until you check the date.</p>
        <form className="stack" onSubmit={doCapture}>
          <textarea className="textarea" name="text" rows={3} required minLength={3} placeholder="Reminder: Lab 6 report due Friday 14 Nov by 11:59 pm on Moodle." />
          <button className="btn" type="submit" disabled={capture.busy}>{capture.busy ? 'Reading…' : 'Find deadlines'}</button>
        </form>
        <ErrorNote>{capture.error}</ErrorNote>
        {captured && (
          <div className="note" style={{ flexDirection: 'column' }}>
            <span className="small">{captured.message}</span>
            {captured.items.map((w) => <Link key={w.id} to={`/work/${w.id}`}>{w.title} · {w.due_at ? dueLabel(w.due_at) : 'no date found'}</Link>)}
          </div>
        )}
      </section>

      <section className="panel stack">
        <h3>Import a file</h3>
        <p className="muted small">A CSV with columns like <code>title,due,subject</code>, a JSON list, a calendar <code>.ics</code> file, or an export from the earlier UniTask. Importing twice doesn't create duplicates.</p>
        <form className="row" style={{ gap: 8, flexWrap: 'wrap' }} onSubmit={importFile}>
          <input name="file" type="file" accept=".csv,.json,.ics" required />
          <button className="btn" type="submit" disabled={file.busy}>{file.busy ? 'Importing…' : 'Import'}</button>
        </form>
        <ErrorNote>{file.error}</ErrorNote>
        {fileResult && <div className="note ok">{fileResult}</div>}
      </section>

      <section className="panel stack">
        <div className="spread">
          <h3>VTOP browser extension</h3>
          {vtop && <span className="pill ok">Last sent {vtop.last_synced_at ? relative(vtop.last_synced_at) : '—'}</span>}
        </div>
        <p className="muted small">
          VTOP has no public API, so UniTask doesn't log in for you. Instead, the extension reads the assignment pages <em>you</em> open while signed in, and sends only what's on screen to your account with a token.
          The extension is included in the project (<code>extension/vtop</code>) and has not yet been tested against the live VTOP site.
        </p>
        {vtop?.last_result && <p className="small">Last batch: {counts(vtop.last_result)}</p>}
        {token ? (
          <div className="note" style={{ flexDirection: 'column' }}>
            <span className="small">Copy this into the extension's options. It is shown once; creating a new one revokes it.</span>
            <code style={{ wordBreak: 'break-all', fontSize: 12 }}>{token}</code>
          </div>
        ) : (
          <div className="row" style={{ gap: 8 }}>
            <button className="btn small" type="button" disabled={ext.busy} onClick={() => ext.run(async () => { setToken((await api.post<{ token: string }>('/api/extension/token')).token); await reload() })}>
              {data?.extension_token ? 'Create a new token' : 'Create extension token'}
            </button>
            {data?.extension_token && <button className="btn small ghost danger" type="button" onClick={() => ext.run(async () => { await api.del('/api/extension/token'); await reload() })}>Revoke</button>}
          </div>
        )}
        <ErrorNote>{ext.error}</ErrorNote>
      </section>
    </div>
  )
}
