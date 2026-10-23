import type { LucideIcon } from 'lucide-react'

interface MetricCardProps {
  label: string
  value: string | number
  footnote: string
  icon: LucideIcon
  tone?: 'purple' | 'amber' | 'red' | 'teal'
}

export function MetricCard({ label, value, footnote, icon: Icon, tone = 'purple' }: MetricCardProps) {
  return (
    <article className="metric-card">
      <div className="metric-head">
        <span>{label}</span>
        <span className={`metric-icon${tone === 'purple' ? '' : ` ${tone}`}`}><Icon size={16} /></span>
      </div>
      <div className="metric-value">{value}</div>
      <div className="metric-foot">{footnote}</div>
    </article>
  )
}
