export type Role = 'student' | 'teacher'
export type Source = 'unitask' | 'teams' | 'personal'
export type SubmissionStatus = 'assigned' | 'working' | 'turned_in' | 'returned'
export type Tier = 'missed' | 'overdue' | 'now' | 'soon' | 'later' | 'someday'

export interface User {
  id: number
  email: string
  name: string
  role: Role
}

export interface AuthResponse {
  token: string | null
  user: User | null
  needs_confirmation: boolean
  message: string | null
}

export interface CourseBrief {
  id: number
  name: string
  code: string
  color: string
  source: Source
}

export interface Course extends CourseBrief {
  description: string | null
  my_role: 'teacher' | 'student' | 'owner'
  teacher_name: string | null
  join_code: string | null
  student_count: number
  open_count: number
}

export interface Change {
  id: number
  kind: 'created' | 'due_changed' | 'title_changed' | 'removed'
  old_value: string | null
  new_value: string | null
  detected_at: string
  seen: boolean
}

export interface Priority {
  score: number
  tier: Tier
  reason: string
  start_by: string | null
  hours_left: number | null
  effort_minutes: number
}

export interface WorkItem {
  id: number
  title: string
  instructions: string | null
  course: CourseBrief | null
  source: Source
  external_url: string | null
  due_at: string | null
  points: number | null
  allow_late: boolean
  attachment_name: string | null
  removed_at_source: boolean
  status: SubmissionStatus
  effort_minutes: number | null
  text: string | null
  file_name: string | null
  submitted_at: string | null
  grade: number | null
  feedback: string | null
  submission_id: number | null
  changes: Change[]
  priority: Priority
}

export interface FeedChange {
  id: number
  work_id: number
  title: string
  kind: Change['kind']
  old_value: string | null
  new_value: string | null
  detected_at: string
  source: Source
}

export interface Today {
  next: WorkItem | null
  focus: WorkItem[]
  upcoming: WorkItem[]
  overdue: WorkItem[]
  changes: FeedChange[]
  teams: { configured: boolean; status: TeamsState; last_synced_at: string | null; account: string | null }
}

export interface PlanBlock {
  item_id: number
  title: string
  course: CourseBrief | null
  minutes: number
  finishes_item: boolean
  note: string
}

export interface Plan {
  minutes: number
  blocks: PlanBlock[]
  left_over: number
  skipped: string[]
}

export interface TeacherWork {
  id: number
  course_id: number
  course_name: string
  title: string
  instructions: string | null
  due_at: string | null
  points: number | null
  allow_late: boolean
  attachment_name: string | null
  created_at: string
  total: number
  turned_in: number
  returned: number
  late: number
}

export interface Member {
  id: number
  name: string
  email: string
  joined_at: string
}

export interface SubmissionRow {
  id: number | null
  student: Member
  status: SubmissionStatus
  submitted_at: string | null
  late: boolean
  text: string | null
  file_name: string | null
  grade: number | null
  feedback: string | null
}

export type TeamsState = 'not_connected' | 'connected' | 'needs_consent' | 'expired' | 'error'

export interface TeamsStatus {
  configured: boolean
  status: TeamsState
  account: string | null
  last_synced_at: string | null
  last_error: string | null
  last_result: {
    classes: number
    assignments: number
    new: number
    updated: number
    due_changed: number
    removed: number
    turned_in: number
    notes: string[]
  } | null
  auto_sync_minutes: number
}

const TOKEN_KEY = 'unitask.token'

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY)
  } catch {
    return null
  }
}

export function setToken(token: string | null) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token)
    else localStorage.removeItem(TOKEN_KEY)
  } catch {
    // Private mode: the session simply won't survive a reload.
  }
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

let onUnauthorized: (() => void) | null = null
export function setUnauthorizedHandler(handler: () => void) {
  onUnauthorized = handler
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = {}
  const token = getToken()
  if (token) headers.Authorization = `Bearer ${token}`
  let payload: BodyInit | undefined
  if (body instanceof FormData) payload = body
  else if (body !== undefined) {
    headers['Content-Type'] = 'application/json'
    payload = JSON.stringify(body)
  }
  let response: Response
  try {
    response = await fetch(path, { method, headers, body: payload })
  } catch {
    throw new ApiError(0, 'Could not reach the UniTask server. Is the backend running?')
  }
  if (response.status === 401 && token) onUnauthorized?.()
  if (!response.ok) {
    let message = `Request failed (${response.status})`
    try {
      const data = await response.json()
      if (typeof data.detail === 'string') message = data.detail
      else if (Array.isArray(data.detail) && data.detail[0]?.msg) message = data.detail[0].msg.replace(/^Value error, /, '')
    } catch {
      // Non-JSON error body; keep the generic message.
    }
    throw new ApiError(response.status, message)
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

export const api = {
  get: <T>(path: string) => request<T>('GET', path),
  post: <T>(path: string, body?: unknown) => request<T>('POST', path, body),
  patch: <T>(path: string, body?: unknown) => request<T>('PATCH', path, body),
  del: <T = void>(path: string) => request<T>('DELETE', path),
}

/** Opens a stored file through a short-lived link from the API. */
export async function openFile(path: string) {
  // Open the tab synchronously so popup blockers treat it as part of the click.
  const tab = window.open('about:blank', '_blank')
  try {
    const { url } = await api.get<{ url: string; name: string }>(path)
    if (tab) {
      tab.opener = null
      tab.location.href = url
    } else {
      window.location.href = url
    }
  } catch (error) {
    tab?.close()
    throw error
  }
}
