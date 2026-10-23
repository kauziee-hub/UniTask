import { useContext } from 'react'
import { AppDataContext } from './AppDataStore'

export function useAppData() {
  const context = useContext(AppDataContext)
  if (!context) throw new Error('useAppData must be used inside AppDataProvider.')
  return context
}
