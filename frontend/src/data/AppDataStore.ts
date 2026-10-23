import { createContext } from 'react'
import type { Assignment, Subject } from './sampleData'

export interface AppDataContextValue {
  assignments: Assignment[]
  subjects: Subject[]
  saveAssignment: (assignment: Omit<Assignment, 'id'>, id?: string) => void
  deleteAssignment: (id: string) => void
  completeAssignment: (id: string) => void
  saveSubject: (subject: Omit<Subject, 'id'>, id?: string) => void
  deleteSubject: (id: string) => void
  importAssignments: (items: Omit<Assignment, 'id'>[]) => number
  resetDemoData: () => void
}

export const AppDataContext = createContext<AppDataContextValue | null>(null)
