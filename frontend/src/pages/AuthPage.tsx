import { useState, type FormEvent } from 'react'
import { Command } from 'lucide-react'
import { Link } from 'react-router-dom'

interface AuthPageProps {
  mode: 'login' | 'register'
}

export function AuthPage({ mode }: AuthPageProps) {
  const [showNotice, setShowNotice] = useState(false)
  const isRegister = mode === 'register'

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setShowNotice(true)
  }

  return (
    <main className="auth-layout">
      <aside className="auth-aside">
        <Link to="/" className="auth-brand" style={{ textDecoration: 'none' }}>
          <span className="brand-mark"><Command size={18} /></span>
          UniTask AI
        </Link>
        <div className="auth-message">
          <h1>Your semester, in sync.</h1>
          <p>Bring your assignments, deadlines, and study plans into one calm, focused workspace.</p>
        </div>
        <div className="auth-aside-footer">A little more clarity, one deadline at a time.</div>
      </aside>
      <section className="auth-main">
        <div className="auth-form-wrap">
          <Link to="/" className="auth-mobile-brand"><span className="brand-mark"><Command size={17} /></span>UniTask AI</Link>
          <h2>{isRegister ? 'Create your account' : 'Welcome back'}</h2>
          <p className="auth-intro">{isRegister ? 'Start organizing your academic life today.' : 'Sign in to continue to your workspace.'}</p>
          <form onSubmit={handleSubmit}>
            {isRegister && <div className="form-field"><label htmlFor="name">Full name</label><input id="name" name="name" autoComplete="name" placeholder="Alex Morgan" required /></div>}
            <div className="form-field"><label htmlFor="email">University email</label><input id="email" name="email" type="email" autoComplete="email" placeholder="you@university.edu" required /></div>
            <div className="form-field"><label htmlFor="password">Password</label><input id="password" name="password" type="password" autoComplete={isRegister ? 'new-password' : 'current-password'} placeholder="At least 8 characters" minLength={8} required /></div>
            {isRegister && <div className="form-field"><label htmlFor="university">University <span style={{ color: 'var(--muted)', fontWeight: 400 }}>(optional)</span></label><input id="university" name="university" autoComplete="organization" placeholder="Your university" /></div>}
            <button className="primary-button auth-submit" type="submit">{isRegister ? 'Create account' : 'Sign in'}</button>
          </form>
          {showNotice && <div className="auth-note" role="status">Authentication is not connected yet. This form is a visual foundation only; no account was created or signed in.</div>}
          <div className="auth-switch">
            {isRegister ? 'Already have an account? ' : 'New to UniTask AI? '}
            <Link to={isRegister ? '/login' : '/register'}>{isRegister ? 'Sign in' : 'Create an account'}</Link>
          </div>
        </div>
      </section>
    </main>
  )
}
