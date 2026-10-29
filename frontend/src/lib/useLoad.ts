import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from './api'

/** Load JSON from the API; `reload()` refetches without clearing what is on screen. */
export function useLoad<T>(path: string | null) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(Boolean(path))
  const latest = useRef(path)

  const reload = useCallback(async () => {
    if (!path) return
    latest.current = path
    setLoading(true)
    try {
      const result = await api.get<T>(path)
      if (latest.current === path) {
        setData(result)
        setError(null)
      }
    } catch (err) {
      if (latest.current === path) setError(err instanceof Error ? err.message : 'Something went wrong.')
    } finally {
      if (latest.current === path) setLoading(false)
    }
  }, [path])

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void reload()
  }, [reload])

  return { data, setData, error, loading, reload }
}
