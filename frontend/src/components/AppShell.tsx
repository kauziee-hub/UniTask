import { useState } from 'react'
import {
  Bell,
  BookOpen,
  CalendarDays,
  CheckSquare,
  ChevronDown,
  CircleHelp,
  Command,
  FileUp,
  LayoutDashboard,
  Menu,
  Moon,
  PanelLeftClose,
  PanelLeftOpen,
  Search,
  Settings,
  Sparkles,
  Sun,
  Unplug,
} from 'lucide-react'
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useAppData } from '../data/useAppData'

const navigation = [
  { label: 'Dashboard', to: '/', icon: LayoutDashboard },
  { label: 'Assignments', to: '/assignments', icon: CheckSquare, badge: '9' },
  { label: 'Calendar', to: '/calendar', icon: CalendarDays },
  { label: 'Subjects', to: '/subjects', icon: BookOpen },
  { label: 'AI Assistant', to: '/assistant', icon: Sparkles },
  { label: 'Timetable & import', to: '/timetable', icon: FileUp },
]

const tools = [
  { label: 'Integrations', to: '/integrations', icon: Unplug },
  { label: 'Settings', to: '/settings', icon: Settings },
]

export function AppShell() {
  const [collapsed, setCollapsed] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)
  const [darkMode, setDarkMode] = useState(document.documentElement.dataset.theme === 'dark')
  const [searchQuery, setSearchQuery] = useState('')
  const { assignments } = useAppData()
  const pendingCount = assignments.filter((assignment) => assignment.status !== 'Completed').length
  const location = useLocation()
  const navigate = useNavigate()
  const pageName = navigation.concat(tools).find((item) => item.to === location.pathname)?.label ?? 'Not found'

  const toggleTheme = () => {
    const nextTheme = darkMode ? 'light' : 'dark'
    document.documentElement.dataset.theme = nextTheme
    setDarkMode(!darkMode)
  }

  const renderLinks = (items: typeof navigation) => items.map(({ label, to, icon: Icon, badge }) => (
    <NavLink
      key={to}
      to={to}
      end={to === '/'}
      className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}
      onClick={() => setMobileOpen(false)}
      aria-label={label}
    >
      <Icon size={17} strokeWidth={1.8} />
      <span>{label}</span>
      {(badge || to === '/assignments') && <span className="nav-badge">{to === '/assignments' ? pendingCount : badge}</span>}
    </NavLink>
  ))

  return (
    <div className="app-shell">
      <button
        className={`mobile-overlay${mobileOpen ? ' visible' : ''}`}
        type="button"
        aria-label="Close navigation menu"
        onClick={() => setMobileOpen(false)}
      />
      <aside className={`sidebar${collapsed ? ' is-collapsed' : ''}${mobileOpen ? ' mobile-open' : ''}`}>
        <div className="brand-row">
          <div className="brand-mark"><Command size={18} strokeWidth={2.4} /></div>
          <span className="brand-name">UniTask<span style={{ color: 'var(--primary)' }}> AI</span></span>
        </div>
        <div className="nav-label">Workspace</div>
        <nav className="nav-list" aria-label="Workspace navigation">{renderLinks(navigation)}</nav>
        <div className="nav-label" style={{ marginTop: 27 }}>Manage</div>
        <nav className="nav-list" aria-label="Settings navigation">{renderLinks(tools)}</nav>
        <div className="sidebar-bottom">
          <div className="semester-card">
            <div className="semester-title">Fall semester</div>
            <div className="semester-subtitle">2026 · Week 8 of 16</div>
          </div>
          <div className="user-card">
            <div className="avatar">AM</div>
            <div className="user-details">
              <div className="user-name">Alex Morgan</div>
              <div className="user-email">Computer Science</div>
            </div>
            <ChevronDown size={14} style={{ marginLeft: 'auto', color: 'var(--muted)' }} />
          </div>
        </div>
      </aside>

      <main className={`main-area${collapsed ? ' is-wide' : ''}`}>
        <header className="topbar">
          <div className="topbar-leading">
            <button className="mobile-menu-button" type="button" onClick={() => setMobileOpen(true)} aria-label="Open navigation">
              <Menu size={19} />
            </button>
            <button
              className="icon-button collapse-button"
              type="button"
              onClick={() => setCollapsed(!collapsed)}
              aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
              title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            >
              {collapsed ? <PanelLeftOpen size={17} /> : <PanelLeftClose size={17} />}
            </button>
            <span className="eyebrow" style={{ margin: 0 }}>{pageName}</span>
          </div>
          <div className="topbar-actions">
            <label className="search-box">
              <Search size={15} />
              <input
                aria-label="Search assignments"
                placeholder="Search assignments..."
                value={searchQuery}
                onChange={(event) => setSearchQuery(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' && searchQuery.trim()) {
                    navigate(`/assignments?search=${encodeURIComponent(searchQuery.trim())}`)
                  }
                }}
              />
              <span className="search-shortcut">⌘ K</span>
            </label>
            <button className="icon-button" type="button" onClick={toggleTheme} aria-label={`Switch to ${darkMode ? 'light' : 'dark'} theme`} title="Toggle theme">
              {darkMode ? <Sun size={17} /> : <Moon size={17} />}
            </button>
            <button className="icon-button" type="button" aria-label="Help" title="Help">
              <CircleHelp size={17} />
            </button>
            <button className="icon-button" type="button" aria-label="Notifications" title="Notifications">
              <Bell size={17} /><span className="notification-dot" />
            </button>
            <span className="top-divider" />
            <div className="avatar avatar-small topbar-profile">AM</div>
          </div>
        </header>
        <Outlet />
      </main>
    </div>
  )
}
