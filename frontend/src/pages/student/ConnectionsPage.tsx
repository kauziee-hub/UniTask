import { useEffect, useState } from 'react'
import { RefreshCw } from 'lucide-react'
import { useSearchParams } from 'react-router-dom'
import { ErrorNote, Spinner, Toast } from '../../components/ui'
import { api, type TeamsStatus } from '../../lib/api'
import { relative } from '../../lib/format'
import { useLoad } from '../../lib/useLoad'
import { MoreConnections } from './MoreConnections'

const OUTCOMES: Record<string, string> = {
  synced: 'Teams connected and your assignments are synced.',
  connected: 'Teams connected.',
  needs_consent: 'Microsoft blocked the connection. See the details below.',
  expired: 'That sign-in link expired. Try connecting again.',
  error: 'Teams connection failed. See the details below.',
}

const READS = [
  ['Your Teams classes', 'Class names, so assignments are grouped properly.'],
  ['Assignments posted to you', 'Title, due date, points, instructions and the link back to Teams.'],
  ['Whether you turned each one in', 'So finished work drops off your list.'],
]

export function ConnectionsPage() {
  const [params, setParams] = useSearchParams()
  const { data, setData, error, loading } = useLoad<TeamsStatus>('/api/integrations/teams')
  const [busy, setBusy] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [toast, setToast] = useState<string | null>(() => OUTCOMES[params.get('teams') ?? ''] ?? null)

  useEffect(() => {
    if (params.has('teams')) setParams({}, { replace: true })
  }, [params, setParams])

  const connect = async () => {
    setBusy('connect')
    setActionError(null)
    try {
      const { auth_url } = await api.post<{ auth_url: string }>('/api/integrations/teams/connect')
      window.location.href = auth_url
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Could not start the Microsoft sign-in.')
      setBusy(null)
    }
  }

  const sync = async () => {
    setBusy('sync')
    try {
      const status = await api.post<TeamsStatus>('/api/integrations/teams/sync')
      setData(status)
      setToast(status.status === 'connected' ? 'Checked Teams. Your list is up to date.' : null)
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Sync failed.')
    } finally {
      setBusy(null)
    }
  }

  const disconnect = async (removeItems: boolean) => {
    const message = removeItems
      ? 'Disconnect Teams and remove all synced Teams assignments from UniTask?'
      : 'Disconnect Teams? Synced assignments stay, but stop updating.'
    if (!window.confirm(message)) return
    setBusy('disconnect')
    await api.del(`/api/integrations/teams?remove_items=${removeItems}`)
    setData(await api.get<TeamsStatus>('/api/integrations/teams'))
    setBusy(null)
  }

  const result = data?.last_result

  return (
    <main className="page narrow">
      <p className="kicker">Teams sync</p>
      <h1 className="title" style={{ marginTop: 8 }}>Microsoft Teams</h1>
      <p className="lede">
        Connect once with your college Microsoft account. After that, assignments your teachers post in Teams show up in
        UniTask on their own. So do changed due dates and anything you've already turned in.
      </p>

      <ErrorNote>{error}</ErrorNote>
      {!data && loading && <div style={{ marginTop: 24 }}><Spinner /></div>}

      {data && (
        <div className="panel" style={{ marginTop: 28 }}>
          {!data.configured ? (
            <>
              <p style={{ fontWeight: 500 }}>Teams sync isn't set up on this server yet</p>
              <p className="muted" style={{ marginTop: 6 }}>
                Whoever runs this UniTask server needs to register it with Microsoft Entra and set{' '}
                <span className="mono">MS_CLIENT_ID</span> and <span className="mono">MS_CLIENT_SECRET</span>. Steps are in{' '}
                <span className="mono">docs/TEAMS_SETUP.md</span>.
              </p>
            </>
          ) : data.status === 'connected' ? (
            <>
              <div className="spread">
                <div className="row">
                  <span className="dot live" />
                  <div>
                    <p style={{ fontWeight: 500 }}>Connected{data.account ? ` as ${data.account}` : ''}</p>
                    <p className="muted" style={{ fontSize: 13 }}>
                      {data.last_synced_at ? `Last checked ${relative(data.last_synced_at)}` : 'Not synced yet'}
                      {data.auto_sync_minutes > 0 && ` · checks again every ${data.auto_sync_minutes} min`}
                    </p>
                  </div>
                </div>
                <button className="btn" type="button" onClick={sync} disabled={busy !== null}>
                  <RefreshCw size={14} /> {busy === 'sync' ? 'Checking…' : 'Check now'}
                </button>
              </div>
              {result && (
                <dl className="facts" style={{ marginBottom: 0 }}>
                  <div><dt>Classes</dt><dd className="mono">{result.classes}</dd></div>
                  <div><dt>Assignments</dt><dd className="mono">{result.assignments}</dd></div>
                  <div><dt>New last check</dt><dd className="mono">{result.new}</dd></div>
                  <div><dt>Dates moved</dt><dd className="mono">{result.due_changed}</dd></div>
                </dl>
              )}
              {result?.notes.map((note) => <p key={note} className="muted" style={{ fontSize: 13, marginTop: 10 }}>{note}</p>)}
            </>
          ) : (
            <>
              {data.status === 'needs_consent' && (
                <div className="note teams" style={{ marginBottom: 16, flexDirection: 'column' }}>
                  <strong>Your college's Microsoft 365 needs to approve UniTask</strong>
                  <span>{data.last_error}</span>
                </div>
              )}
              {(data.status === 'expired' || data.status === 'error') && data.last_error && (
                <div className="note error" style={{ marginBottom: 16 }}>{data.last_error}</div>
              )}
              <p style={{ fontWeight: 500 }}>What UniTask reads</p>
              <ul className="list" style={{ margin: '10px 0 18px' }}>
                {READS.map(([what, why]) => (
                  <li key={what} style={{ padding: '8px 0', borderTop: '1px solid var(--rule)' }}>
                    <span style={{ fontWeight: 500 }}>{what}</span>
                    <span className="muted" style={{ display: 'block', fontSize: 13 }}>{why}</span>
                  </li>
                ))}
              </ul>
              <p className="muted" style={{ fontSize: 13, marginBottom: 16 }}>
                Read-only. UniTask never posts, submits or messages anything in Teams, and never sees your password:
                you sign in on Microsoft's own page.
              </p>
              <button className="btn teams" type="button" onClick={connect} disabled={busy !== null} style={{ height: 40 }}>
                {busy === 'connect' ? 'Opening Microsoft sign-in…' : data.status === 'not_connected' ? 'Connect Microsoft Teams' : 'Reconnect Teams'}
              </button>
            </>
          )}
          <div style={{ marginTop: 12 }}><ErrorNote>{actionError}</ErrorNote></div>
        </div>
      )}

      {data?.configured && data.status !== 'not_connected' && (
        <div className="row" style={{ marginTop: 18 }}>
          <button className="btn ghost small" type="button" onClick={() => disconnect(false)} disabled={busy !== null}>Disconnect</button>
          <button className="btn ghost small danger" type="button" onClick={() => disconnect(true)} disabled={busy !== null}>
            Disconnect and remove Teams items
          </button>
        </div>
      )}

      <MoreConnections />
      <Toast message={toast} onDone={() => setToast(null)} />
    </main>
  )
}
