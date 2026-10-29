import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import {
  ArrowRight,
  BrainCircuit,
  CalendarClock,
  CalendarRange,
  FileText,
  GraduationCap,
  Inbox,
  Layers,
  LifeBuoy,
  Library,
  Plus,
  Search,
  Siren,
  Sunrise,
  BarChart3,
  type LucideIcon,
} from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { api, type WorkItem } from '../lib/api'
import { dueLabel } from '../lib/format'
import type { Subject } from '../lib/types'

interface Entry {
  key: string
  group: string
  icon: LucideIcon
  title: ReactNode
  sub?: string
  hint?: string
  run: () => void | Promise<void>
}

interface Hit {
  material_id: number
  title: string
  page: number
  excerpt: string
}

const PAGES: [string, string, LucideIcon][] = [
  ['/', 'Today', Sunrise],
  ['/inbox', 'Inbox', Inbox],
  ['/work', 'Deadlines', CalendarClock],
  ['/planner', 'Planner', CalendarRange],
  ['/exams', 'Exams & rescue', Siren],
  ['/subjects', 'Subjects & syllabus', Layers],
  ['/library', 'Library', Library],
  ['/revision', 'Revision', GraduationCap],
  ['/tutor', 'Tutor', BrainCircuit],
  ['/insights', 'Insights', BarChart3],
]

/** Ctrl/⌘+K: jump anywhere, find any deadline or subject, search inside your notes, or capture a task. */
export function CommandPalette({ open, onClose, onRecovery }: { open: boolean; onClose: () => void; onRecovery: () => void }) {
  const navigate = useNavigate()
  const dialog = useRef<HTMLDialogElement>(null)
  const input = useRef<HTMLInputElement>(null)
  const [query, setQuery] = useState('')
  const [selected, setSelected] = useState(0)
  const [work, setWork] = useState<WorkItem[]>([])
  const [subjects, setSubjects] = useState<Subject[]>([])
  const [hits, setHits] = useState<Hit[]>([])
  const [status, setStatus] = useState<string | null>(null)

  useEffect(() => {
    const d = dialog.current
    if (!d) return
    if (open && !d.open) {
      d.showModal()
      setQuery('')
      setStatus(null)
      setSelected(0)
      input.current?.focus()
      api.get<WorkItem[]>('/api/work').then(setWork).catch(() => undefined)
      api.get<Subject[]>('/api/subjects').then(setSubjects).catch(() => undefined)
    }
    if (!open && d.open) d.close()
  }, [open])

  // Search inside the student's own materials once the query is specific enough.
  useEffect(() => {
    const q = query.trim()
    if (q.length < 3) return
    const timer = window.setTimeout(() => {
      api
        .get<{ hits: Hit[] }>(`/api/search?q=${encodeURIComponent(q)}`)
        .then((r) => setHits(r.hits.slice(0, 5)))
        .catch(() => setHits([]))
    }, 220)
    return () => window.clearTimeout(timer)
  }, [query])

  const go = (to: string) => {
    onClose()
    navigate(to)
  }

  const entries = useMemo<Entry[]>(() => {
    const q = query.trim().toLowerCase()
    const match = (text: string) => !q || text.toLowerCase().includes(q)
    const list: Entry[] = []
    if (!q) {
      list.push({ key: 'recovery', group: 'Actions', icon: LifeBuoy, title: "I'm behind — make a recovery plan", sub: 'What to do, what to push, where to ask for more time', run: () => { onClose(); onRecovery() } })
      list.push({ key: 'add', group: 'Actions', icon: Plus, title: 'Capture a task', sub: 'Type it naturally: “DBMS assignment due Friday 5pm”', run: () => document.querySelector<HTMLInputElement>('.palette-input input')?.focus() })
    }
    for (const [to, label, icon] of PAGES) if (match(label)) list.push({ key: `p${to}`, group: 'Go to', icon, title: label, run: () => go(to) })
    if (q) {
      for (const item of work.filter((w) => match(w.title)).slice(0, 6)) {
        list.push({
          key: `w${item.id}`,
          group: 'Deadlines',
          icon: CalendarClock,
          title: item.title,
          sub: [item.course?.name, item.due_at ? `due ${dueLabel(item.due_at)}` : 'no due date'].filter(Boolean).join(' · '),
          run: () => go(`/work/${item.id}`),
        })
      }
      for (const s of subjects.filter((s) => match(s.name) || match(s.code ?? '')).slice(0, 4)) {
        list.push({ key: `s${s.id}`, group: 'Subjects', icon: Layers, title: s.name, sub: s.code || undefined, run: () => go(`/subjects/${s.id}`) })
      }
      for (const h of q.length >= 3 ? hits : []) {
        list.push({ key: `h${h.material_id}-${h.page}`, group: 'In your notes', icon: FileText, title: `${h.title} · page ${h.page}`, sub: h.excerpt, run: () => go(`/library/${h.material_id}?page=${h.page}`) })
      }
      list.push({ key: 'ask', group: 'Ask', icon: BrainCircuit, title: <>Ask the tutor: “{query.trim()}”</>, sub: 'Answered from your own notes, with page references', run: () => go(`/library?tab=ask&q=${encodeURIComponent(query.trim())}`) })
      list.push({
        key: 'capture',
        group: 'Ask',
        icon: Plus,
        title: <>Capture as a task: “{query.trim()}”</>,
        sub: 'Dates in your text are read and marked unconfirmed until you check them',
        run: async () => {
          setStatus('Reading your text…')
          try {
            const r = await api.post<{ items: WorkItem[] }>('/api/capture', { text: query.trim() })
            if (r.items[0]) go(`/work/${r.items[0].id}`)
            else setStatus('Nothing to capture in that text.')
          } catch (err) {
            setStatus(err instanceof Error ? err.message : 'Could not capture.')
          }
        },
      })
    }
    return list
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query, work, subjects, hits])

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setSelected((i) => Math.min(entries.length - 1, i + 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setSelected((i) => Math.max(0, i - 1))
    } else if (e.key === 'Enter') {
      e.preventDefault()
      void entries[selected]?.run()
    }
  }

  let lastGroup = ''
  return (
    <dialog ref={dialog} className="palette" onClose={onClose} onClick={(e) => e.target === dialog.current && onClose()} aria-label="Search and commands">
      <div className="palette-input">
        <Search size={17} aria-hidden="true" />
        <input
          ref={input}
          value={query}
          onChange={(e) => { setQuery(e.target.value); setSelected(0) }}
          onKeyDown={onKey}
          placeholder="Search deadlines, subjects, your notes — or type a new task"
          aria-label="Search or type a command"
        />
        <span className="kbd">Esc</span>
      </div>
      <ul className="palette-list" role="listbox">
        {entries.map((entry, index) => {
          const header = entry.group !== lastGroup ? entry.group : null
          lastGroup = entry.group
          const Icon = entry.icon
          return (
            <li key={entry.key}>
              {header && <div className="palette-group">{header}</div>}
              <button
                type="button"
                className="palette-item"
                role="option"
                aria-selected={index === selected}
                onMouseEnter={() => setSelected(index)}
                onClick={() => void entry.run()}
              >
                <Icon size={16} strokeWidth={1.7} />
                <span style={{ minWidth: 0 }}>
                  <span className="clip" style={{ display: 'block' }}>{entry.title}</span>
                  {entry.sub && <span className="sub">{entry.sub}</span>}
                </span>
                {index === selected && <ArrowRight size={14} className="muted" />}
              </button>
            </li>
          )
        })}
      </ul>
      <div className="palette-foot">
        {status ? <span>{status}</span> : <><span>↑↓ to move</span><span>Enter to open</span><span>Ctrl K anywhere</span></>}
      </div>
    </dialog>
  )
}
