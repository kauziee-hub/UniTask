import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { api, getToken, setToken, setUnauthorizedHandler, type AuthResponse, type Role, type User } from './api'

interface AuthContextValue {
  user: User | null
  loading: boolean
  demoEnabled: boolean
  enterDemo: (role: Role) => Promise<AuthResponse>
  login: (email: string, password: string) => Promise<AuthResponse>
  demoLogin: (role: Role) => Promise<AuthResponse>
  register: (name: string, email: string, password: string, role: Role) => Promise<AuthResponse>
  confirm: (email: string, code: string) => Promise<AuthResponse>
  logout: () => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(() => Boolean(getToken()))
  const [demoEnabled, setDemoEnabled] = useState(false)

  useEffect(() => {
    api.get<{ demo_enabled: boolean }>('/api/auth/config')
      .then((config) => setDemoEnabled(config.demo_enabled))
      .catch(() => setDemoEnabled(false))
  }, [])

  const logout = useCallback(() => {
    setToken(null)
    setUser(null)
  }, [])

  useEffect(() => {
    setUnauthorizedHandler(logout)
    if (!getToken()) return
    api
      .get<User>('/api/auth/me')
      .then(setUser)
      .catch(() => setToken(null))
      .finally(() => setLoading(false))
  }, [logout])

  const accept = useCallback((response: AuthResponse) => {
    if (response.token && response.user) {
      setToken(response.token)
      setUser(response.user)
    }
    return response
  }, [])

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      loading,
      demoEnabled,
      enterDemo: (role) => api.post<AuthResponse>(`/api/auth/demo?role=${role}`, {}).then(accept),
      logout,
      login: (email, password) => api.post<AuthResponse>('/api/auth/login', { email, password }).then(accept),
      demoLogin: (role) => api.post<AuthResponse>('/api/auth/demo-login', { role }).then(accept),
      register: (name, email, password, role) =>
        api.post<AuthResponse>('/api/auth/register', { name, email, password, role }).then(accept),
      confirm: (email, code) => api.post<AuthResponse>('/api/auth/confirm', { email, code }),
    }),
    [user, loading, demoEnabled, logout, accept],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used inside AuthProvider')
  return context
}
