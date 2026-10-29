const DAY = 86_400_000

function startOfDay(date: Date) {
  const copy = new Date(date)
  copy.setHours(0, 0, 0, 0)
  return copy
}

export function dayDiff(iso: string, now = new Date()) {
  return Math.round((startOfDay(new Date(iso)).getTime() - startOfDay(now).getTime()) / DAY)
}

/** "in 14h", "in 3 days", "2h ago" */
export function relative(iso: string, now = new Date()) {
  const ms = new Date(iso).getTime() - now.getTime()
  const abs = Math.abs(ms)
  const minutes = Math.round(abs / 60_000)
  const hours = Math.round(abs / 3_600_000)
  const days = Math.round(abs / DAY)
  let text: string
  if (minutes < 60) text = `${Math.max(minutes, 1)} min`
  else if (hours < 36) text = `${hours}h`
  else text = `${days} days`
  return ms >= 0 ? `in ${text}` : `${text} ago`
}

const time = new Intl.DateTimeFormat(undefined, { hour: 'numeric', minute: '2-digit' })
const weekday = new Intl.DateTimeFormat(undefined, { weekday: 'short' })
const dayMonth = new Intl.DateTimeFormat(undefined, { day: 'numeric', month: 'short' })
const full = new Intl.DateTimeFormat(undefined, { weekday: 'long', day: 'numeric', month: 'long' })

/** "Today, 11:59 PM", "Tomorrow, 9:00 AM", "Fri, 9:00 AM", "14 Nov, 5:00 PM" */
export function dueLabel(iso: string, now = new Date()) {
  const date = new Date(iso)
  const diff = dayDiff(iso, now)
  const clock = time.format(date)
  if (diff === 0) return `Today, ${clock}`
  if (diff === 1) return `Tomorrow, ${clock}`
  if (diff === -1) return `Yesterday, ${clock}`
  if (diff > 1 && diff < 7) return `${weekday.format(date)}, ${clock}`
  return `${dayMonth.format(date)}, ${clock}`
}

export function longDate(date = new Date()) {
  return full.format(date)
}

export function shortDate(iso: string) {
  return dayMonth.format(new Date(iso))
}

export function minutesLabel(minutes: number) {
  if (minutes < 60) return `${minutes} min`
  const h = Math.floor(minutes / 60)
  const m = minutes % 60
  return m ? `${h}h ${m}m` : `${h}h`
}

/** Value for <input type="datetime-local"> from an ISO string, in local time. */
export function toLocalInput(iso: string | null) {
  if (!iso) return ''
  const date = new Date(iso)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`
}

/** ISO string (with the user's offset applied) from a datetime-local value. */
export function fromLocalInput(value: string) {
  return value ? new Date(value).toISOString() : null
}

export type Bucket = 'Overdue' | 'Today' | 'Tomorrow' | 'This week' | 'Later' | 'No due date'

export function bucketFor(iso: string | null, now = new Date()): Bucket {
  if (!iso) return 'No due date'
  if (new Date(iso).getTime() < now.getTime()) return 'Overdue'
  const diff = dayDiff(iso, now)
  if (diff <= 0) return 'Today'
  if (diff === 1) return 'Tomorrow'
  if (diff < 7) return 'This week'
  return 'Later'
}

export function initials(name: string) {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join('')
}
