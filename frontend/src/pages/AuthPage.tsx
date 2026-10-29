import { useEffect, useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ErrorNote } from '../components/ui'
import { api, type Role } from '../lib/api'
import { useAuth } from '../lib/auth'

export function AuthPage({ mode }: { mode: 'login' | 'register' }) {
  const { login, register, confirm, demoLogin, demoEnabled, enterDemo } = useAuth()
  const [demo, setDemo] = useState(false)
  const navigate = useNavigate()
  const [role, setRole] = useState<Role>('student')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  useEffect(() => {
    api.get<{ demo: boolean }>('/api/auth/config').then((c) => {
      setDemo(c.demo)
      // Demo servers: the sign-in form starts filled with the demo student so presenting takes one click.
      if (c.demo && mode === 'login') {
        setEmail((v) => v || 'riya.sharma@example.edu')
        setPassword((v) => v || 'demo-student-2026')
      }
    }).catch(() => undefined)
  }, [mode])
  const [error, setError] = useState<string | null>(null)
  const [info, setInfo] = useState<string | null>(null)
  const [confirming, setConfirming] = useState(false)
  const [busy, setBusy] = useState(false)
  const isRegister = mode === 'register'

  const openDemo = async (demoRole: Role) => {
    setBusy(true)
    setError(null)
    try {
      await enterDemo(demoRole)
      navigate('/')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not open the demo.')
    } finally {
      setBusy(false)
    }
  }

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    setBusy(true)
    setError(null)
    try {
      if (confirming) {
        const response = await confirm(email, String(form.get('code')))
        setConfirming(false)
        setInfo(response.message)
        navigate('/login')
        return
      }
      const password = String(form.get('password'))
      const response = isRegister
        ? await register(String(form.get('name')), email, password, role)
        : await login(email, password)
      if (response.needs_confirmation) {
        setConfirming(true)
        setInfo(response.message)
      } else {
        navigate('/')
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="auth">
      <section className="auth-story">
        <span className="wordmark" style={{ padding: 0 }}>UniTask</span>
        <div>
          <p className="kicker">For students who have too much due</p>
          <h1 className="display" style={{ marginTop: 16 }}>
            Know what to do <em>next</em>, not just what's due.
          </h1>
          <div className="auth-points">
            <div><span>01</span><span>Your Teams assignments arrive on their own. No copying deadlines by hand.</span></div>
            <div><span>02</span><span>Everything is ranked by how much work it needs against how little time is left.</span></div>
            <div><span>03</span><span>Tell it you have two free hours and it tells you how to spend them.</span></div>
            <div><span>04</span><span>Teachers post work, students turn it in, and grades come back in the same place.</span></div>
          </div>
        </div>
        <p className="muted" style={{ fontSize: 12.5 }}>Built for VIT students and faculty.</p>
      </section>

      <section className="auth-form">
        {demoEnabled ? (
          <div style={{ display: 'grid', gap: 20, width: '100%', maxWidth: 380 }}>
            <div>
              <p className="kicker">Cloud Architecture demonstration</p>
              <h2 className="title" style={{ marginTop: 12 }}>Try UniTask</h2>
              <p className="muted" style={{ marginTop: 8 }}>Open the prepared workspace. No signup needed.</p>
            </div>
            <ErrorNote>{error}</ErrorNote>
            <button className="btn primary" type="button" disabled={busy} onClick={() => void openDemo('student')}>
              {busy ? 'Opening workspace…' : 'Open student demo'}
            </button>
            <button className="btn" type="button" disabled={busy} onClick={() => void openDemo('teacher')}>Open teacher demo</button>
            <p className="muted" style={{ fontSize: 13 }}>Shared demonstration with synthetic courses, notes and assignments. Changes are visible to other demo visitors.</p>
          </div>
        ) : (
        <form onSubmit={submit}>
          <div>
            <h2 className="title">{confirming ? 'Check your email' : isRegister ? 'Create an account' : 'Sign in'}</h2>
            <p className="muted" style={{ marginTop: 6 }}>
              {confirming
                ? `Enter the code sent to ${email}.`
                : isRegister
                  ? 'Takes less than a minute.'
                  : 'Welcome back.'}
            </p>
          </div>

          {info && <div className="note ok">{info}</div>}
          <ErrorNote>{error}</ErrorNote>

          {confirming ? (
            <label className="field">
              <span>Verification code</span>
              <input className="input mono" name="code" inputMode="numeric" autoComplete="one-time-code" required />
            </label>
          ) : (
            <>
              {isRegister && (
                <>
                  <fieldset className="role-pick" style={{ border: 0, padding: 0, margin: 0 }}>
                    <legend className="sr-only">I am a</legend>
                    <label>
                      <input type="radio" name="role" checked={role === 'student'} onChange={() => setRole('student')} />
                      <strong>Student</strong>
                      <small>Track and finish work</small>
                    </label>
                    <label>
                      <input type="radio" name="role" checked={role === 'teacher'} onChange={() => setRole('teacher')} />
                      <strong>Teacher</strong>
                      <small>Run classes, grade work</small>
                    </label>
                  </fieldset>
                  <label className="field">
                    <span>Full name</span>
                    <input className="input" name="name" autoComplete="name" required maxLength={120} />
                  </label>
                </>
              )}
              <label className="field">
                <span>Email</span>
                <input
                  className="input"
                  name="email"
                  type="email"
                  autoComplete="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />
              </label>
              <label className="field">
                <span>Password {isRegister && <span className="hint">· at least 8 characters</span>}</span>
                <input
                  className="input"
                  name="password"
                  type="password"
                  autoComplete={isRegister ? 'new-password' : 'current-password'}
                  minLength={isRegister ? 8 : 1}
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
              </label>
            </>
          )}

          <button className="btn primary" type="submit" disabled={busy} style={{ height: 40 }}>
            {busy ? 'One moment…' : confirming ? 'Verify' : isRegister ? 'Create account' : 'Sign in'}
          </button>

          {demo && !demoEnabled && !confirming && (
            <div className="demo-entry">
              <span className="kicker">Or explore the demo workspace</span>
              <div className="row" style={{ gap: 8 }}>
                <button className="btn" type="button" disabled={busy} onClick={() => demoLogin('student').then(() => navigate('/')).catch((e) => setError(e.message))}>As a student</button>
                <button className="btn" type="button" disabled={busy} onClick={() => demoLogin('teacher').then(() => navigate('/')).catch((e) => setError(e.message))}>As a teacher</button>
              </div>
              <span className="tiny muted">Synthetic data, clearly labelled “(Demo)”. Nothing real.</span>
            </div>
          )}

          {!confirming && (
            <p className="muted" style={{ fontSize: 13 }}>
              {isRegister ? 'Already have an account? ' : 'New here? '}
              <Link to={isRegister ? '/login' : '/register'}>{isRegister ? 'Sign in' : 'Create an account'}</Link>
            </p>
          )}
        </form>
        )}
      </section>
    </main>
  )
}
