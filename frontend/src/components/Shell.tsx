import { useEffect, useState } from 'react'
import { BookOpen, CalendarClock, LogOut, Menu, Moon, PlugZap, Sun, Sunrise } from 'lucide-react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from '../lib/auth'
import { initials } from '../lib/format'

function currentTheme(): 'light' | 'dark' {
  const forced = document.documentElement.dataset.theme
  if (forced === 'light' || forced === 'dark') return forced
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

export function Shell() {
  const { user, logout } = useAuth()
  const [open, setOpen] = useState(false)
  const [theme, setTheme] = useState(currentTheme)
  const { pathname } = useLocation()
  useEffect(() => {
    window.scrollTo(0, 0)
  }, [pathname])
  if (!user) return null

  const links =
    user.role === 'student'
      ? [
          { to: '/', label: 'Today', icon: Sunrise, end: true },
          { to: '/work', label: 'Deadlines', icon: CalendarClock },
          { to: '/classes', label: 'Classes', icon: BookOpen },
          { to: '/connections', label: 'Teams sync', icon: PlugZap },
        ]
      : [{ to: '/', label: 'Classes', icon: BookOpen, end: true }]

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
        <nav aria-label="Main">
          {links.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) => `nav${isActive ? ' active' : ''}`}
              onClick={() => setOpen(false)}
            >
              <Icon size={16} strokeWidth={1.7} />
              {label}
            </NavLink>
          ))}
        </nav>
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
      <div>
        <div className="mobile-bar">
          <button className="btn ghost icon" type="button" onClick={() => setOpen(true)} aria-label="Open menu">
            <Menu size={18} />
          </button>
          <span className="wordmark" style={{ fontSize: 22, padding: 0 }}>UniTask</span>
        </div>
        <Outlet />
      </div>
    </div>
  )
}
