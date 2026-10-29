import { useCallback, useState } from 'react'

/** Run a button's async work with a busy flag and a readable error. */
export function useAction() {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const run = useCallback(async <T,>(work: () => Promise<T>): Promise<T | undefined> => {
    setBusy(true)
    setError(null)
    try {
      return await work()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong.')
      return undefined
    } finally {
      setBusy(false)
    }
  }, [])
  return { busy, error, setError, run }
}
