import { useState } from 'react'
import { login, register } from './api'
import ThemeToggle from './ThemeToggle'

const EMAIL = /^[^@\s]+@[^@\s]+\.[^@\s]+$/

// Mirrors the server's rules so common mistakes are caught before a round
// trip; the server still checks everything.
function validate(mode, form) {
  if (mode === 'register' && !form.name.trim()) return 'Enter your name.'
  if (!EMAIL.test(form.email.trim())) return 'Enter a valid email address.'
  if (mode === 'register' && form.password.length < 8) return 'Use a password of at least 8 characters.'
  if (!form.password) return 'Enter your password.'
  return ''
}

export default function AuthPage({ onSignedIn }) {
  const [mode, setMode] = useState('login')
  const [form, setForm] = useState({ name: '', email: '', password: '' })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const switchTo = (next) => {
    setMode(next)
    setError('')
  }

  const submit = async (e) => {
    e.preventDefault()
    setError('')
    const problem = validate(mode, form)
    if (problem) return setError(problem)
    setBusy(true)
    try {
      const credentials = { email: form.email.trim(), password: form.password }
      const user = mode === 'register'
        ? await register({ ...credentials, name: form.name.trim() })
        : await login(credentials)
      onSignedIn(user)
    } catch (err) {
      setError(err.message)
      setBusy(false)
    }
  }

  const field = (key) => (e) => setForm({ ...form, [key]: e.target.value })
  const isRegister = mode === 'register'

  return (
    <div className="auth-shell">
      <div className="auth-top">
        <ThemeToggle />
      </div>
      <main className="auth-card panel">
        <div className="brand auth-brand">
          <span className="brand-mark" aria-hidden="true">₹</span>
          LodgeLedger
        </div>
        <p className="auth-tagline">Track income and spending, set monthly budgets, and see the risks early.</p>

        <div className="auth-tabs" role="tablist" aria-label="Sign in or create an account">
          <button type="button" role="tab" aria-selected={!isRegister}
            className={isRegister ? 'auth-tab' : 'auth-tab is-active'} onClick={() => switchTo('login')}>
            Sign in
          </button>
          <button type="button" role="tab" aria-selected={isRegister}
            className={isRegister ? 'auth-tab is-active' : 'auth-tab'} onClick={() => switchTo('register')}>
            Create account
          </button>
        </div>

        <form className="auth-form" onSubmit={submit} noValidate>
          {isRegister && (
            <label className="field">
              <span className="field-label">Name</span>
              <input type="text" autoComplete="name" maxLength={80} value={form.name} onChange={field('name')} />
            </label>
          )}
          <label className="field">
            <span className="field-label">Email</span>
            <input type="email" autoComplete="email" maxLength={254} value={form.email} onChange={field('email')} />
          </label>
          <label className="field">
            <span className="field-label">Password</span>
            <input
              type="password" maxLength={128} value={form.password} onChange={field('password')}
              autoComplete={isRegister ? 'new-password' : 'current-password'}
              aria-describedby={isRegister ? 'password-hint' : undefined}
            />
            {isRegister && <span id="password-hint" className="auth-hint">At least 8 characters.</span>}
          </label>
          {error && <p className="notice" role="alert">{error}</p>}
          <button type="submit" className="btn auth-submit" disabled={busy}>
            {busy ? 'Please wait…' : isRegister ? 'Create account' : 'Sign in'}
          </button>
        </form>
      </main>
    </div>
  )
}
