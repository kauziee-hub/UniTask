export type AssignmentStatus = 'Not started' | 'In progress' | 'Completed'

export interface Subject {
  id: string
  name: string
  code: string
  color: string
}

export interface Assignment {
  id: string
  title: string
  subjectId: string
  dueDate: string
  status: AssignmentStatus
  platform: string
  priorityReason?: string
}

export const subjects: Subject[] = [
  { id: 'cs301', name: 'Compiler Design', code: 'CS301', color: '#4f46e5' },
  { id: 'cs305', name: 'Database Systems', code: 'CS305', color: '#0d9488' },
  { id: 'cs309', name: 'Computer Networks', code: 'CS309', color: '#f59e0b' },
  { id: 'ma201', name: 'Probability & Statistics', code: 'MA201', color: '#ec4899' },
]

export const dateInDays = (days: number) => {
  const date = new Date()
  date.setDate(date.getDate() + days)
  return date
}

export const formatDateInput = (date: Date) => {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

export const daysUntilDue = (dueDate: string) => {
  const due = new Date(`${dueDate}T00:00:00`)
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  return Math.round((due.getTime() - today.getTime()) / 86_400_000)
}

export const assignments: Assignment[] = [
  { id: 'a1', title: 'Lexer & Parser Implementation', subjectId: 'cs301', dueDate: formatDateInput(dateInDays(1)), status: 'In progress', platform: 'Moodle', priorityReason: 'Due tomorrow · 15 marks' },
  { id: 'a2', title: 'Normalization Case Study', subjectId: 'cs305', dueDate: formatDateInput(dateInDays(2)), status: 'Not started', platform: 'Google Classroom', priorityReason: 'Due soon · high priority' },
  { id: 'a3', title: 'TCP Congestion Control Lab', subjectId: 'cs309', dueDate: formatDateInput(dateInDays(4)), status: 'Not started', platform: 'Moodle' },
  { id: 'a4', title: 'Bayesian Inference Problem Set', subjectId: 'ma201', dueDate: formatDateInput(dateInDays(5)), status: 'In progress', platform: 'Manual entry' },
  { id: 'a5', title: 'Syntax-Directed Translation Quiz', subjectId: 'cs301', dueDate: formatDateInput(dateInDays(0)), status: 'Not started', platform: 'Moodle' },
  { id: 'a6', title: 'ER Diagram Design', subjectId: 'cs305', dueDate: formatDateInput(dateInDays(7)), status: 'Not started', platform: 'Google Classroom' },
  { id: 'a7', title: 'Code Generation Worksheet', subjectId: 'cs301', dueDate: formatDateInput(dateInDays(9)), status: 'Not started', platform: 'Moodle' },
  { id: 'a8', title: 'Query Optimization Exercises', subjectId: 'cs305', dueDate: formatDateInput(dateInDays(11)), status: 'Not started', platform: 'Google Classroom' },
  { id: 'a9', title: 'Routing Protocol Report', subjectId: 'cs309', dueDate: formatDateInput(dateInDays(12)), status: 'Not started', platform: 'Moodle' },
  { id: 'a10', title: 'Probability Review Questions', subjectId: 'ma201', dueDate: formatDateInput(dateInDays(14)), status: 'Not started', platform: 'Manual entry' },
  { id: 'a11', title: 'Compiler Design Mini Project', subjectId: 'cs301', dueDate: formatDateInput(dateInDays(16)), status: 'Not started', platform: 'Moodle' },
]

export const formatDueDate = (dueDate: string) => {
  const days = daysUntilDue(dueDate)
  if (days === 0) return 'Today'
  if (days === 1) return 'Tomorrow'
  if (days === -1) return 'Yesterday'
  return new Date(`${dueDate}T00:00:00`).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

export const getSubject = (subjectId: string) => subjects.find((subject) => subject.id === subjectId)
