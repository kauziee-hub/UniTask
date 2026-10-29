import { useState } from 'react'
import { X } from 'lucide-react'
import { Link } from 'react-router-dom'
import { Empty, ErrorNote, PageHead, Spinner, Tabs } from '../../components/ui'
import { api } from '../../lib/api'
import { relative } from '../../lib/format'
import type { InboxItem } from '../../lib/types'
import { useLoad } from '../../lib/useLoad'

const KIND_LABEL: Record<string, string> = {
  new_work: 'New work',
  due_changed: 'Deadline moved',
  removed: 'Removed at source',
  material_ready: 'Library',
  reminder: 'Reminder',
  sync_error: 'Needs attention',
  graded: 'Graded',
  announcement: 'Announcement',
}
const TONE: Record<string, string> = { due_changed: 'accent', removed: 'accent', sync_error: 'accent', reminder: 'warn', new_work: 'teams', material_ready: 'ok' }

export function InboxPage() {
  const [filter, setFilter] = useState<'all' | 'deadlines' | 'library' | 'problems'>('all')
  const { data, error, loading, setData, reload } = useLoad<{ unread: number; items: InboxItem[] }>('/api/inbox')

  const mark = async (item: InboxItem, action: 'read' | 'dismiss') => {
    const updated = await api.post<InboxItem>(`/api/inbox/${item.id}/${action}`)
    setData((current) =>
      current && {
        unread: current.unread - (item.read ? 0 : 1),
        items: action === 'dismiss' ? current.items.filter((i) => i.id !== item.id) : current.items.map((i) => (i.id === item.id ? updated : i)),
      },
    )
  }

  const readAll = async () => {
    await api.post('/api/inbox/read-all')
    await reload()
  }

  const groups = {
    all: () => true,
    deadlines: (i: InboxItem) => ['new_work', 'due_changed', 'removed', 'reminder'].includes(i.kind),
    library: (i: InboxItem) => i.kind === 'material_ready',
    problems: (i: InboxItem) => i.kind === 'sync_error',
  }
  const items = (data?.items ?? []).filter(groups[filter])

  return (
    <main className="page narrow">
      <PageHead kicker="Academic inbox" title="What changed">
        {data && data.unread > 0 && <button className="btn small" type="button" onClick={readAll}>Mark all read</button>}
      </PageHead>
      <p className="muted" style={{ marginTop: -10, marginBottom: 18 }}>
        New assignments, moved or removed deadlines, reminders, processed files and sync problems, from every connected source.
      </p>
      <Tabs
        value={filter}
        onChange={setFilter}
        tabs={[
          { key: 'all', label: 'Everything', count: data?.unread },
          { key: 'deadlines', label: 'Deadlines' },
          { key: 'library', label: 'Library' },
          { key: 'problems', label: 'Problems' },
        ]}
      />
      <ErrorNote>{error}</ErrorNote>
      {loading && !data && <Spinner />}
      {data && items.length === 0 && <Empty title="Nothing here">When something changes in your courses, it shows up here once — never twice.</Empty>}
      <div>
        {items.map((item) => (
          <div key={item.id} className={`inbox-row${item.read ? ' read' : ''}`}>
            <span className="dot live" />
            <div style={{ minWidth: 0 }}>
              <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
                <span className={`pill ${TONE[item.kind] ?? ''}`}>{KIND_LABEL[item.kind] ?? item.kind}</span>
                {item.source !== 'unitask' && <span className="muted tiny">via {item.source}</span>}
                <span className="muted tiny mono">{relative(item.created_at)}</span>
              </div>
              <div style={{ marginTop: 4 }}>
                {item.link ? (
                  <Link to={item.link} onClick={() => !item.read && mark(item, 'read')}><strong>{item.title}</strong></Link>
                ) : (
                  <strong>{item.title}</strong>
                )}
              </div>
              {item.body && <p className="muted small" style={{ marginTop: 2 }}>{item.body}</p>}
            </div>
            <div className="row" style={{ gap: 4 }}>
              {!item.read && <button className="btn ghost small" type="button" onClick={() => mark(item, 'read')}>Read</button>}
              <button className="btn ghost icon small" type="button" aria-label="Dismiss" onClick={() => mark(item, 'dismiss')}><X size={14} /></button>
            </div>
          </div>
        ))}
      </div>
    </main>
  )
}
