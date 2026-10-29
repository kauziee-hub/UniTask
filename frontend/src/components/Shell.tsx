import { useEffect, useState } from 'react'
import {
  BarChart3,
  BookOpen,
  BrainCircuit,
  CalendarClock,
  CalendarRange,
  GraduationCap,
  Inbox,
  Layers,
  Library,
  LifeBuoy,
  LogOut,
  Search,
  Menu,
  Moon,
  PlugZap,
  Settings,
  Siren,
  Sun,
  Sunrise,
  type LucideIcon,
} from 'lucide-react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { CommandPalette } from './CommandPalette'
import { RecoverySheet } from './Recovery'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'
import { initials } from '../lib/format'

function currentTheme(): 'light' | 'dark' {
  const forced = document.documentElement.dataset.theme
  if (forced === 'light' || forced === 'dark') return forced
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

interface Link {
  to: string
  label: string
  icon: LucideIcon
  end?: boolean
  badge?: number
}

export function Shell() {
  const { user, logout } = useAuth()
  const [open, setOpen] = useState(false)
  const [theme, setTheme] = useState(currentTheme)
  const [unread, setUnread] = useState(0)
  const [palette, setPalette] = useState(false)
  const [recovery, setRecovery] = useState(false)
  const { pathname } = useLocation()

  // Ctrl/⌘+K opens search and commands from anywhere (students only).
  useEffect(() => {
    if (user?.role !== 'student') return
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        setPalette(true)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [user?.role])

  useEffect(() => {
    window.scrollTo(0, 0)
    if (user?.role !== 'student') return
    let cancelled = false
    api
      .get<{ unread: number }>('/api/inbox')
      .then((data) => !cancelled && setUnread(data.unread))
      .catch(() => undefined)
    return () => {
      cancelled = true
    }
  }, [pathname, user?.role])

  if (!user) return null

  const groups: { label?: string; links: Link[] }[] =
    user.role === 'student'
      ? [
          {
            links: [
              { to: '/', label: 'Today', icon: Sunrise, end: true },
              { to: '/inbox', label: 'Inbox', icon: Inbox, badge: unread },
            ],
          },
          {
            label: 'Plan',
            links: [
              { to: '/work', label: 'Deadlines', icon: CalendarClock },
              { to: '/planner', label: 'Planner', icon: CalendarRange },
              { to: '/exams', label: 'Exams', icon: Siren },
            ],
          },
          {
            label: 'Learn',
            links: [
              { to: '/subjects', label: 'Subjects', icon: Layers },
              { to: '/library', label: 'Library', icon: Library },
              { to: '/revision', label: 'Revision', icon: GraduationCap },
              { to: '/tutor', label: 'Tutor', icon: BrainCircuit },
              { to: '/insights', label: 'Insights', icon: BarChart3 },
            ],
          },
          {
            label: 'Connect',
            links: [
              { to: '/classes', label: 'Classes', icon: BookOpen },
              { to: '/connections', label: 'Connections', icon: PlugZap },
              { to: '/settings', label: 'Settings', icon: Settings },
            ],
          },
        ]
      : [{ links: [{ to: '/', label: 'Classes', icon: BookOpen, end: true }] }]

  const toggleTheme = () => {
    const next = theme === 'dark' ? 'light' : 'dark'
    document.documentElement.dataset.theme = next
    try {
      localStorage.setItem('unitask.theme', next)
    } catch {
      // Theme just won't persist.
    }
    setTheme(next)
  }

  return (
    <div className="shell">
      {open && <button className="scrim" type="button" aria-label="Close menu" onClick={() => setOpen(false)} />}
      <aside className={`rail${open ? ' open' : ''}`}>
        <NavLink to="/" className="wordmark" onClick={() => setOpen(false)}>
          UniTask <small>{user.role === 'teacher' ? 'faculty' : 'student'}</small>
        </NavLink>
        {groups.map((group, index) => (
          <nav key={index} className="rail-group" aria-label={group.label ?? 'Main'}>
            {group.label && <span className="rail-label">{group.label}</span>}
            {group.links.map(({ to, label, icon: Icon, end, badge }) => (
              <NavLink key={to} to={to} end={end} className={({ isActive }) => `nav${isActive ? ' active' : ''}`} onClick={() => setOpen(false)}>
                <Icon size={16} strokeWidth={1.7} />
                {label}
                {badge ? <span className="badge" aria-label={`${badge} unread`}>{badge > 99 ? '99+' : badge}</span> : null}
              </NavLink>
            ))}
          </nav>
        ))}
        <div className="rail-foot">
          <div className="who">
            <span className="monogram">{initials(user.name)}</span>
            <span style={{ minWidth: 0 }}>
              <span className="name" style={{ display: 'block' }}>{user.name}</span>
              <span className="role">{user.role}</span>
            </span>
          </div>
          <div className="rail-actions">
            <button className="btn ghost small" type="button" onClick={toggleTheme} aria-label="Toggle dark mode">
              {theme === 'dark' ? <Sun size={14} /> : <Moon size={14} />}
            </button>
            <button className="btn ghost small" type="button" onClick={logout}>
              <LogOut size={14} /> Sign out
            </button>
          </div>
        </div>
      </aside>
      <div style={{ minWidth: 0 }}>
        <div className="mobile-bar">
          <button className="btn ghost icon" type="button" onClick={() => setOpen(true)} aria-label="Open menu">
            <Menu size={18} />
          </button>
          <span className="wordmark" style={{ fontSize: 22, padding: 0 }}>UniTask</span>
          {user.role === 'student' && unread > 0 && (
            <NavLink to="/inbox" className="pill accent" style={{ marginLeft: 'auto', textDecoration: 'none' }}>{unread} new</NavLink>
          )}
        </div>
        {user.role === 'student' && (
          <div className="topbar">
            <button className="cmd-trigger" type="button" onClick={() => setPalette(true)} aria-label="Search and commands">
              <Search size={15} />
              <span>Search deadlines, notes, subjects… or type a task</span>
              <kbd>Ctrl K</kbd>
            </button>
            <span className="spacer" />
            <button className="btn small" type="button" onClick={() => setRecovery(true)}>
              <LifeBuoy size={14} /> I'm behind
            </button>
          </div>
        )}
        <Outlet />
        {user.role === 'student' && (
          <>
            <CommandPalette open={palette} onClose={() => setPalette(false)} onRecovery={() => setRecovery(true)} />
            <RecoverySheet open={recovery} onClose={() => setRecovery(false)} />
          </>
        )}
      </div>
    </div>
  )
}
