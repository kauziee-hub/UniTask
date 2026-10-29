import { useState } from 'react'
import { ArrowRight, ExternalLink, RefreshCw } from 'lucide-react'
import { Link } from 'react-router-dom'
import { WorkRow } from '../../components/WorkRow'
import { Empty, ErrorNote, SourcePill, Spinner } from '../../components/ui'
import { api, type FeedChange, type Plan, type Today } from '../../lib/api'
import { dueLabel, longDate, minutesLabel, relative } from '../../lib/format'
import { useLoad } from '../../lib/useLoad'

const FREE_TIME = [30, 60, 120, 180, 240]

function ChangeLine({ change }: { change: FeedChange }) {
  const label = { created: 'New', due_changed: 'Moved', title_changed: 'Renamed', removed: 'Removed' }[change.kind]
  const tone = change.kind === 'removed' || (change.kind === 'due_changed' && (change.new_value ?? '') < (change.old_value ?? ''))
    ? 'var(--accent)'
    : change.source === 'teams'
      ? 'var(--teams)'
      : 'var(--ink-2)'
  return (
    <li className="change">
      <span className="kind" style={{ color: tone }}>{label}</span>
      <span>
        <Link to={`/work/${change.work_id}`} style={{ fontWeight: 500 }}>{change.title}</Link>
        {change.kind === 'due_changed' && (
          <span className="muted">
            {' '}· <span className="strike">{change.old_value ? dueLabel(change.old_value) : 'no date'}</span> →{' '}
            <span style={{ color: 'var(--ink)' }}>{change.new_value ? dueLabel(change.new_value) : 'no date'}</span>
          </span>
        )}
        {change.kind === 'created' && change.new_value && <span className="muted"> · due {dueLabel(change.new_value)}</span>}
        {change.kind === 'removed' && <span className="muted"> · no longer in Teams</span>}
        {change.kind === 'title_changed' && <span className="muted"> · was “{change.old_value}”</span>}
        <span className="muted mono" style={{ marginLeft: 8, fontSize: 11 }}>{relative(change.detected_at)}</span>
      </span>
    </li>
  )
}

function Planner() {
  const [minutes, setMinutes] = useState<number | null>(null)
  const { data: plan, loading, error } = useLoad<Plan>(minutes ? `/api/plan?minutes=${minutes}` : null)

  return (
    <section className="planner" aria-label="Plan free time">
      <div className="spread">
        <div>
          <h2 style={{ fontSize: 15, fontWeight: 600 }}>Got some free time?</h2>
          <p className="muted" style={{ fontSize: 13 }}>Pick how long you have. UniTask fills it with whatever matters most.</p>
        </div>
        <div className="segmented" role="group" aria-label="Free time">
          {FREE_TIME.map((value) => (
            <button key={value} type="button" aria-pressed={minutes === value} onClick={() => setMinutes(value)}>
              {minutesLabel(value)}
            </button>
          ))}
        </div>
      </div>
      {loading && <div style={{ marginTop: 14 }}><Spinner /></div>}
      <ErrorNote>{error}</ErrorNote>
      {plan && !loading && (
        plan.blocks.length === 0 ? (
          <p className="muted" style={{ marginTop: 14 }}>Nothing pending. Take the break.</p>
        ) : (
          <>
            <div className="timeline" aria-hidden="true">
              {plan.blocks.map((block) => (
                <div
                  key={block.item_id}
                  style={{ flex: block.minutes, background: block.course?.color ?? '#6b665c' }}
                  title={block.title}
                >
                  {block.title}
                </div>
              ))}
              {plan.left_over > 0 && <div style={{ flex: plan.left_over, color: 'var(--muted)' }}>free</div>}
            </div>
            <ol className="list plan-steps">
              {plan.blocks.map((block) => (
                <li key={block.item_id}>
                  <span>
                    <Link to={`/work/${block.item_id}`} style={{ fontWeight: 500 }}>{block.title}</Link>
                    <span className="muted" style={{ display: 'block', fontSize: 12.5 }}>{block.note}</span>
                  </span>
                  <span className="mono">{minutesLabel(block.minutes)}{block.finishes_item ? ' · done' : ''}</span>
                </li>
              ))}
            </ol>
            {plan.skipped.length > 0 && (
              <p className="muted" style={{ fontSize: 12.5, marginTop: 6 }}>
                Doesn't fit this time: {plan.skipped.join(', ')}
              </p>
            )}
          </>
        )
      )}
    </section>
  )
}

export function TodayPage() {
  const { data, error, loading, reload } = useLoad<Today>('/api/today')
  const [syncing, setSyncing] = useState(false)

  const syncNow = async () => {
    setSyncing(true)
    try {
      await api.post('/api/integrations/teams/sync')
      await reload()
    } finally {
      setSyncing(false)
    }
  }

  const dismissChanges = async () => {
    await api.post('/api/changes/seen')
    await reload()
  }

  const next = data?.next
  const nothingDue = data && !next && data.overdue.length === 0

  return (
    <main className="page">
      <p className="kicker">{longDate()}</p>
      <ErrorNote>{error}</ErrorNote>
      {!data && loading && <div style={{ marginTop: 30 }}><Spinner /></div>}

      {data && (
        <>
          <section className="hero">
            {next ? (
              <>
                <p className="kicker" style={{ color: next.priority.tier === 'overdue' ? 'var(--accent)' : undefined }}>
                  {next.priority.tier === 'overdue' ? 'Overdue — do this first' : 'Do this next'}
                </p>
                <h1 className="display">{next.title}</h1>
                <div className="hero-meta">
                  {next.course && (
                    <span className="row" style={{ gap: 7 }}>
                      <span className="swatch" style={{ background: next.course.color }} />
                      {next.course.name}
                    </span>
                  )}
                  {next.due_at && <span className="mono">Due {dueLabel(next.due_at)}</span>}
                  <SourcePill source={next.source} />
                </div>
                <p className="lede">{next.priority.reason}.</p>
                <div className="hero-actions">
                  <Link className="btn primary" to={`/work/${next.id}`}>
                    Open <ArrowRight size={15} />
                  </Link>
                  {next.source === 'teams' && next.external_url && (
                    <a className="btn" href={next.external_url} target="_blank" rel="noreferrer">
                      Open in Teams <ExternalLink size={14} />
                    </a>
                  )}
                </div>
              </>
            ) : (
              <>
                <h1 className="display" style={{ marginTop: 14 }}>
                  {nothingDue ? <>Nothing due. <em>Enjoy it.</em></> : 'All caught up.'}
                </h1>
                <p className="lede">
                  {data.teams.status === 'connected'
                    ? 'Teams has nothing pending for you. New assignments will show up here on their own.'
                    : 'Connect Microsoft Teams and your assignments will show up here without you typing them in.'}
                </p>
              </>
            )}
          </section>

          {data.changes.length > 0 && (
            <>
              <div className="section-head">
                <h2>What changed since you last looked</h2>
                <button className="btn ghost small" type="button" onClick={dismissChanges}>Mark as seen</button>
              </div>
              <ul className="list">{data.changes.map((c) => <ChangeLine key={c.id} change={c} />)}</ul>
            </>
          )}

          {data.overdue.length > (next?.priority.tier === 'overdue' ? 1 : 0) && (
            <>
              <div className="section-head">
                <h2 style={{ color: 'var(--accent)' }}>Overdue, still accepting work</h2>
                <span className="aside">{data.overdue.length}</span>
              </div>
              <ul className="list">
                {data.overdue.filter((i) => i.id !== next?.id).map((item) => <WorkRow key={item.id} item={item} showReason />)}
              </ul>
            </>
          )}

          {data.focus.filter((i) => i.priority.tier !== 'overdue').length > 0 && (
            <>
              <div className="section-head">
                <h2>Also pressing</h2>
                <span className="aside">ranked by work left vs. time left</span>
              </div>
              <ul className="list">
                {data.focus.filter((i) => i.priority.tier !== 'overdue').map((item) => <WorkRow key={item.id} item={item} showReason />)}
              </ul>
            </>
          )}

          {(next || data.focus.length > 0) && (
            <>
              <div className="section-head"><h2>Plan a session</h2></div>
              <Planner />
            </>
          )}

          {data.upcoming.length > 0 && (
            <>
              <div className="section-head">
                <h2>Coming up</h2>
                <Link className="aside" to="/work">All deadlines →</Link>
              </div>
              <ul className="list">{data.upcoming.map((item) => <WorkRow key={item.id} item={item} />)}</ul>
            </>
          )}

          {nothingDue && data.upcoming.length === 0 && (
            <Empty title="Your list is empty">
              Join a class with a code from your teacher, connect Teams, or add your own task from Deadlines.
            </Empty>
          )}

          <div className="sync-strip">
            {data.teams.status === 'connected' ? (
              <>
                <span className="dot live" />
                <span>
                  Teams connected{data.teams.account ? ` as ${data.teams.account}` : ''}
                  {data.teams.last_synced_at && <> · last checked {relative(data.teams.last_synced_at)}</>}
                </span>
                <button className="btn ghost small" type="button" onClick={syncNow} disabled={syncing} style={{ marginLeft: 'auto' }}>
                  <RefreshCw size={13} className={syncing ? 'spin' : undefined} /> {syncing ? 'Checking…' : 'Check now'}
                </button>
              </>
            ) : data.teams.status === 'not_connected' ? (
              <>
                <span className="dot" />
                <span>Teams isn't connected, so Teams assignments won't appear here.</span>
                <Link className="btn small teams" to="/connections" style={{ marginLeft: 'auto' }}>Connect Teams</Link>
              </>
            ) : (
              <>
                <span className="dot bad" />
                <span>Teams sync needs attention.</span>
                <Link className="btn small" to="/connections" style={{ marginLeft: 'auto' }}>See why</Link>
              </>
            )}
          </div>
        </>
      )}
    </main>
  )
}
