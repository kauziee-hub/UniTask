import type { CourseBrief, WorkItem } from './api'

export type TopicStatus = 'not_started' | 'in_progress' | 'revised' | 'practised'

export interface Action {
  kind: string
  title: string
  reason: string
  label: string
  to: string
  session: SessionStart | null
}

export interface SessionStart {
  kind: 'assignment' | 'topic' | 'revision' | 'rescue'
  coursework_id?: number | null
  topic_id?: number | null
  exam_id?: number | null
  plan_block_id?: number | null
  planned_minutes?: number
  title?: string
}

export interface TimelineRow {
  kind: 'class' | 'lab' | 'tutorial' | 'study' | 'exam' | 'deadline'
  title: string
  start: string
  end: string | null
  location?: string | null
  color?: string | null
  link: string | null
  state?: string
  done?: boolean
  block?: Block
}

export interface InboxItem {
  id: number
  kind: string
  title: string
  body: string | null
  link: string | null
  source: string
  created_at: string
  read: boolean
  dismissed: boolean
}

export interface Session {
  id: number
  kind: string
  title: string
  state: 'active' | 'paused' | 'completed' | 'abandoned'
  planned_minutes: number
  elapsed_seconds: number
  accumulated_seconds: number
  started_at: string
  resumed_at: string | null
  ended_at: string | null
  coursework_id: number | null
  topic_id: number | null
  exam_id: number | null
  plan_block_id: number | null
  scratch: string | null
  checklist: { text: string; done: boolean }[]
  resume: Record<string, unknown> | null
  outcome: string | null
}

export interface WeakTopic {
  topic_id: number
  title: string
  course: CourseBrief | null
  reason: string
  accuracy: number | null
  attempts: number
}

export interface ExamSummary {
  id: number
  title: string
  course: CourseBrief | null
  starts_at: string
  duration_minutes: number
  location: string | null
  notes: string | null
  hours_left: number
  topic_count: number
  covered_count: number
  explicit_topics: boolean
  planned_blocks: number
}

export interface Home {
  now: string
  timezone: string
  next: Action
  today: TimelineRow[]
  radar: WorkItem[]
  overdue: WorkItem[]
  exams: ExamSummary[]
  inbox: { unread: number; items: InboxItem[] }
  study: { sessions: Session[]; due_cards: number; weak_topics: WeakTopic[] }
  progress: {
    minutes_this_week: number
    sessions_completed: number
    items_done: number
    answers: number
    correct: number
    coverage: { course: CourseBrief; total: number; covered: number; started: number }[]
  }
  warnings: { kind: string; text: string; label: string; to: string }[]
  setup: {
    onboarded: boolean
    has_subjects: boolean
    has_work: boolean
    has_timetable: boolean
    has_materials: boolean
    has_exams: boolean
    connections: string[]
  }
  teams: { status: string; last_synced_at: string | null }
}

export interface Subject extends CourseBrief {
  my_role: string
  editable: boolean
  topic_count: number
  coverage: Record<TopicStatus, number>
  covered_pct: number | null
  materials: number
  pyq_count: number
  open_work: number
  unconfirmed: number
  next_exam: { id: number; title: string; starts_at: string } | null
}

export interface TopicNode {
  id: number
  course_id: number
  parent_id: number | null
  title: string
  position: number
  status: TopicStatus
  confirmed: boolean
  origin: string
  est_minutes: number | null
  last_studied_at: string | null
  material_pages: number
  pyq_count: number
  weak_reason: string | null
  prerequisites: { link_id: number; topic_id: number; title: string; suggested: boolean }[]
  topics?: TopicNode[]
}

export interface Syllabus {
  course: CourseBrief
  modules: TopicNode[]
  coverage: Record<TopicStatus, number>
  topic_count: number
  unconfirmed: number
  without_material: string[]
}

export interface Citation {
  label?: string
  material_id: number
  title: string
  page: number
  excerpt: string
}

export interface TopicDetail extends TopicNode {
  course: CourseBrief | null
  module: string | null
  evidence: { attempts: number; correct: number; avg_confidence: number | null; last_at: string | null; weak_reason: string | null }
  pages: { material_id: number; title: string; kind: string; page: number; excerpt: string }[]
  questions: PastQuestion[]
  dependants: { link_id: number; topic_id: number; title: string; suggested: boolean }[]
  cards: number
  memory: { id: number; kind: string; text: string; created_at: string }[]
  recent_attempts: { kind: string; correct: boolean | null; prompt: string | null; created_at: string }[]
  studied_minutes: number
  exams: { id: number; title: string; starts_at: string }[]
}

export interface PastQuestion {
  id: number
  text: string
  year: number | null
  label: string | null
  marks: number | null
  material_id: number
  page: number | null
}

export interface PyqAnalysis {
  note: string
  papers: { id: number; title: string; year: number | null; status: string }[]
  total_questions: number
  groups: { pattern_key: string; count: number; years: number[]; topic_id: number | null; topic: string | null; marks: number | null; questions: PastQuestion[] }[]
  by_topic: { topic_id: number | null; topic: string; count: number }[]
}

export interface Material {
  id: number
  title: string
  filename: string
  kind: string
  course: CourseBrief | null
  content_type: string
  size_bytes: number
  page_count: number | null
  status: 'queued' | 'processing' | 'ready' | 'needs_ocr' | 'failed'
  extractor: string | null
  error: string | null
  year: number | null
  created_at: string
}

export interface MaterialDetail extends Material {
  topics: { topic_id: number; title: string; pages: number[] }[]
  questions: number
  empty_pages: number[]
}

export interface RescuePlan {
  exam: ExamSummary
  mode: string
  mode_label: string
  budget_minutes: number
  free_minutes: number
  needed_minutes: number
  chosen_minutes: number
  feasible: boolean
  message: string
  chosen: {
    order: number
    topic_id: number
    title: string
    module: string
    status: TopicStatus
    minutes: number
    reason: string
    pyq_count: number
    weak: boolean
    has_material: boolean
    materials: { material_id: number; title: string; page: number }[]
  }[]
  excluded: { topic_id: number; title: string; minutes: number; reason: string }[]
  schedule: { topic_id: number; title: string; starts_at: string; ends_at: string }[]
  unscheduled: string[]
  applied?: number
}

export interface Block {
  id: number
  title: string
  kind: string
  state: 'planned' | 'done' | 'missed' | 'skipped'
  starts_at: string
  ends_at: string
  minutes: number
  coursework_id: number | null
  topic_id: number | null
  exam_id: number | null
  reason: string | null
  plan: string
}

export interface Planner {
  window: { start: string; end: string; timezone: string }
  blocks: Block[]
  busy: { title: string; kind: string; starts_at: string; ends_at: string }[]
  forecast: {
    unfit: { key: string; title: string; missing_minutes: number; reason: string; deadline: string | null; coursework_id: number | null; exam_id: number | null; estimated: boolean }[]
    risk: Record<string, 'ok' | 'tight' | 'cannot_fit'>
    load: Record<string, number>
  }
  demands: { key: string; title: string; minutes: number; deadline: string | null; kind: string; estimated: boolean; reason: string }[]
  daily_cap: number
  day_start: string
  day_end: string
  missed: number
  conflicts: { a: string; b: string; a_kind: string; b_kind: string; start: string; end: string }[]
  has_timetable: boolean
  marked_missed?: number
  created?: number
}

export interface TimetableEntry {
  id: number
  title: string
  course: CourseBrief | null
  course_id: number | null
  weekday: number
  start: string
  end: string
  kind: 'class' | 'lab' | 'tutorial'
  location: string | null
  source: string
  confirmed: boolean
}

export interface Card {
  id: number
  front: string
  back: string
  topic_id: number | null
  topic: string | null
  course_id: number | null
  material_id: number | null
  page_no: number | null
  origin: string
  due_at: string
  interval_days: number
  reps: number
  lapses: number
}

export interface Conversation {
  id: number
  mode: 'tutor' | 'ask' | 'explain_back'
  title: string
  course_id: number | null
  topic_id: number | null
  topic: string | null
  created_at: string
  updated_at: string
  messages?: ChatMessage[]
}

export interface ChatMessage {
  id: number
  role: 'user' | 'tutor'
  content: string
  citations: Citation[]
  check: { question: string } | null
  created_at: string
}

export interface Profile {
  user: { id: number; email: string; name: string; role: string }
  university: string | null
  semester: string | null
  timezone: string
  day_start: string
  day_end: string
  daily_study_minutes: number
  pace: 'slow' | 'steady' | 'fast'
  explain_style: 'examples' | 'concise' | 'step_by_step' | 'analogies'
  background: string | null
  attendance_threshold: number | null
  onboarded: boolean
  extension_token: boolean
  ai: AiStatus
}

export interface AiStatus {
  provider: string
  model: string | null
  fast_model?: string | null
  fallback?: string | null
  last_used?: string | null
  available: boolean
  ocr: string
  email: string
}
