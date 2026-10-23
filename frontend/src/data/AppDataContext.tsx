import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { assignments as initialAssignments, subjects as initialSubjects, type Assignment, type Subject } from './sampleData'
import { AppDataContext, type AppDataContextValue } from './AppDataStore'

const STORAGE_KEY = 'unitask-demo-data-v1'

interface AppData {
  assignments: Assignment[]
  subjects: Subject[]
}

function readInitialData(): AppData {
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY)
    if (!stored) return { assignments: initialAssignments, subjects: initialSubjects }
    const parsed = JSON.parse(stored) as Partial<AppData>
    if (!Array.isArray(parsed.assignments) || !Array.isArray(parsed.subjects)) {
      throw new Error('Saved demo data has an unexpected shape.')
    }
    return { assignments: parsed.assignments, subjects: parsed.subjects }
  } catch (error) {
    console.error('Could not read saved UniTask demo data; using the bundled sample data instead.', error)
    return { assignments: initialAssignments, subjects: initialSubjects }
  }
}

export function AppDataProvider({ children }: { children: ReactNode }) {
  const [data, setData] = useState<AppData>(readInitialData)

  useEffect(() => {
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(data))
    } catch (error) {
      console.error('Could not persist UniTask demo data in this browser.', error)
    }
  }, [data])

  const value = useMemo<AppDataContextValue>(() => ({
    ...data,
    saveAssignment: (assignment, id) => {
      setData((current) => ({
        ...current,
        assignments: id
          ? current.assignments.map((item) => item.id === id ? { ...assignment, id } : item)
          : [{ ...assignment, id: crypto.randomUUID() }, ...current.assignments],
      }))
    },
    deleteAssignment: (id) => setData((current) => ({
      ...current,
      assignments: current.assignments.filter((assignment) => assignment.id !== id),
    })),
    completeAssignment: (id) => setData((current) => ({
      ...current,
      assignments: current.assignments.map((assignment) => assignment.id === id
        ? { ...assignment, status: assignment.status === 'Completed' ? 'Not started' : 'Completed' }
        : assignment),
    })),
    saveSubject: (subject, id) => {
      setData((current) => ({
        ...current,
        subjects: id
          ? current.subjects.map((item) => item.id === id ? { ...subject, id } : item)
          : [...current.subjects, { ...subject, id: crypto.randomUUID() }],
      }))
    },
    deleteSubject: (id) => setData((current) => ({
      subjects: current.subjects.filter((subject) => subject.id !== id),
      assignments: current.assignments.filter((assignment) => assignment.subjectId !== id),
    })),
    importAssignments: (items) => {
      const imported = items.map((item) => ({ ...item, id: crypto.randomUUID() }))
      setData((current) => ({ ...current, assignments: [...imported, ...current.assignments] }))
      return imported.length
    },
    resetDemoData: () => setData({ assignments: initialAssignments, subjects: initialSubjects }),
  }), [data])

  return <AppDataContext.Provider value={value}>{children}</AppDataContext.Provider>
}
