import { api } from './api'
import type { Session, SessionStart, TopicStatus } from './types'

/** Start a focus session (or resume the open one for the same assignment/topic). */
export function startSession(payload: SessionStart) {
  return api.post<Session>('/api/sessions', payload)
}

export const STATUSES: { key: TopicStatus; short: string; label: string }[] = [
  { key: 'not_started', short: '–', label: 'Not started' },
  { key: 'in_progress', short: '½', label: 'Started' },
  { key: 'revised', short: 'R', label: 'Revised' },
  { key: 'practised', short: 'P', label: 'Practised' },
]

export const MATERIAL_KINDS = [
  { key: 'notes', label: 'Notes' },
  { key: 'slides', label: 'Slides' },
  { key: 'syllabus', label: 'Syllabus' },
  { key: 'pyq', label: 'Past paper' },
  { key: 'lab_manual', label: 'Lab manual' },
  { key: 'textbook', label: 'Textbook' },
  { key: 'other', label: 'Other' },
]
