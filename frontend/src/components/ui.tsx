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
