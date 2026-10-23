import { CircleAlert, Inbox, LoaderCircle } from 'lucide-react'

export type FeedbackKind = 'loading' | 'empty' | 'error'

interface FeedbackStateProps {
  kind: FeedbackKind
  title: string
  description: string
}

const icons = {
  loading: LoaderCircle,
  empty: Inbox,
  error: CircleAlert,
}

export function FeedbackState({ kind, title, description }: FeedbackStateProps) {
  const Icon = icons[kind]
  return (
    <div className={`feedback-state ${kind}`} role={kind === 'error' ? 'alert' : 'status'} aria-live="polite">
      <Icon size={21} aria-hidden="true" />
      <strong>{title}</strong>
      <span>{description}</span>
    </div>
  )
}
