import { Link } from 'react-router-dom'
import type { WorkItem } from '../lib/api'
import { dueLabel, relative } from '../lib/format'
import { SourcePill, StatusPill } from './ui'

const DONE = new Set(['turned_in', 'returned'])

export function WorkRow({ item, showReason = false }: { item: WorkItem; showReason?: boolean }) {
  const done = DONE.has(item.status)
  const hot = !done && ['overdue', 'now'].includes(item.priority.tier)
  return (
    <li>
      <Link to={`/work/${item.id}`} className={`work-row${done ? ' done' : ''}`}>
        <span className="bar" style={{ background: item.course?.color ?? 'var(--rule-strong)' }} />
        <span style={{ minWidth: 0 }}>
          <span className="work-title" style={{ display: 'block' }}>{item.title}</span>
          <span className="work-meta">
            {item.course && <span>{item.course.name}</span>}
            <SourcePill source={item.source} />
            <StatusPill status={item.status} />
            {item.removed_at_source && <span className="pill accent">Removed in Teams</span>}
            {showReason && !done && <span>{item.priority.reason}</span>}
          </span>
        </span>
        <span className={`due${hot ? ' hot' : ''}`}>
          {item.due_at ? (
            <>
              <span className="when">{dueLabel(item.due_at)}</span>
              {!done && <span className="rel">{relative(item.due_at)}</span>}
            </>
          ) : (
            <span className="rel">No due date</span>
          )}
        </span>
      </Link>
    </li>
  )
}
