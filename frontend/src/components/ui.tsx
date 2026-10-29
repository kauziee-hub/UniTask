import { useEffect, useRef, type ReactNode } from 'react'
import { X } from 'lucide-react'
import type { Source, SubmissionStatus } from '../lib/api'

export function Spinner({ label = 'Loading' }: { label?: string }) {
  return (
    <span className="row muted" role="status">
      <span className="spinner" aria-hidden="true" />
      <span className="sr-only">{label}</span>
    </span>
  )
}

export function ErrorNote({ children }: { children: ReactNode }) {
  if (!children) return null
  return (
    <div className="note error" role="alert">
      {children}
    </div>
  )
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="empty">
      <strong>{title}</strong>
      {children}
    </div>
  )
}

export function SourcePill({ source }: { source: Source }) {
  if (source === 'teams') return <span className="pill teams">Teams</span>
  if (source === 'personal') return <span className="pill">My task</span>
  return null
}

export function StatusPill({ status, late }: { status: SubmissionStatus; late?: boolean }) {
  if (status === 'turned_in') return <span className={`pill ${late ? 'warn' : 'ok'}`}>{late ? 'Turned in late' : 'Turned in'}</span>
  if (status === 'returned') return <span className="pill ok">Returned</span>
  if (status === 'working') return <span className="pill">In progress</span>
  return null
}

export function Sheet({
  open,
  title,
  onClose,
  children,
}: {
  open: boolean
  title: string
  onClose: () => void
  children: ReactNode
}) {
  const ref = useRef<HTMLDialogElement>(null)
  useEffect(() => {
    const dialog = ref.current
    if (!dialog) return
    if (open && !dialog.open) {
      dialog.showModal()
      // React handles autoFocus itself, before the dialog is open; move focus to the first field.
      dialog.querySelector<HTMLElement>('.sheet-body input:not([type=hidden]), .sheet-body textarea, .sheet-body select')?.focus()
    }
    if (!open && dialog.open) dialog.close()
  }, [open])
  return (
    <dialog ref={ref} className="sheet" onClose={onClose} aria-label={title}>
      <div className="sheet-head">
        <h2 className="title" style={{ fontSize: 24 }}>{title}</h2>
        <button className="btn ghost icon" type="button" onClick={onClose} aria-label="Close">
          <X size={16} />
        </button>
      </div>
      <div className="sheet-body">{open && children}</div>
    </dialog>
  )
}

export function Toast({ message, onDone }: { message: string | null; onDone: () => void }) {
  useEffect(() => {
    if (!message) return
    const timer = window.setTimeout(onDone, 4200)
    return () => window.clearTimeout(timer)
  }, [message, onDone])
  if (!message) return null
  return (
    <div className="toast" role="status">
      {message}
    </div>
  )
}

export function Tabs<T extends string>({ tabs, value, onChange }: { tabs: { key: T; label: string; count?: number }[]; value: T; onChange: (key: T) => void }) {
  return (
    <div className="tabs" role="tablist">
      {tabs.map((tab) => (
        <button key={tab.key} type="button" role="tab" aria-selected={value === tab.key} onClick={() => onChange(tab.key)}>
          {tab.label}
          {tab.count !== undefined && tab.count > 0 && <span className="count">{tab.count}</span>}
        </button>
      ))}
    </div>
  )
}

export function Meter({ value, max, tone = 'ink', label }: { value: number; max: number; tone?: 'ink' | 'ok' | 'accent' | 'warn'; label?: string }) {
  const pct = max > 0 ? Math.min(100, Math.round((value / max) * 100)) : 0
  return (
    <span className="meter" role="img" aria-label={label ?? `${value} of ${max}`}>
      <span className={`fill ${tone}`} style={{ width: `${pct}%` }} />
    </span>
  )
}

export function PageHead({ kicker, title, children }: { kicker?: string; title: ReactNode; children?: ReactNode }) {
  return (
    <header className="page-head">
      <div>
        {kicker && <p className="kicker">{kicker}</p>}
        <h1 className="title page-title">{title}</h1>
      </div>
      {children && <div className="row page-actions">{children}</div>}
    </header>
  )
}

const PROVIDER_NAMES: Record<string, string> = { bedrock: 'Amazon Bedrock', gemini: 'Google Gemini' }

/** Names the model that actually answered most recently, so a fallback is never shown as the primary. */
export function AiBadge({ ai }: { ai?: { provider: string; available: boolean; fallback?: string | null; last_used?: string | null } | null }) {
  if (!ai || !ai.available) return <span className="pill">AI off · using your pages only</span>
  const used = ai.last_used ?? ai.provider
  const note = ai.fallback
    ? `Configured: ${PROVIDER_NAMES[ai.provider] ?? ai.provider}, falls back to ${PROVIDER_NAMES[ai.fallback] ?? ai.fallback}`
    : undefined
  return <span className="pill ai" title={note}>{PROVIDER_NAMES[used] ?? used}{ai.last_used && ai.last_used !== ai.provider ? ' (fallback)' : ''}</span>
}
