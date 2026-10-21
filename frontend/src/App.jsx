import { Component, useEffect, useState } from 'react'
import Dashboard from './pages/Dashboard'
import Expenses from './pages/Expenses'
import Income from './pages/Income'
import Savings from './pages/Savings'
import Categories from './pages/Categories'
import Settings from './pages/Settings'
import AuthPage from './AuthPage'
import ThemeToggle from './ThemeToggle'
import { getMe, getToken, logout, onLoggedOut } from './api'
import { todayLabel } from './format'

// "Budget" rather than "Settings": the page holds what you set, so name it after
// that. Month-scoped pages carry today's date as an eyebrow (the month being
// viewed is in each page's own "Showing" control). The divider separates what
// you record daily from what you set up once.
const TABS = [
  { label: 'Overview', Page: Dashboard, dated: true },
  { label: 'Expenses', Page: Expenses, dated: true },
  { label: 'Income', Page: Income, dated: true },
  { label: 'Savings', Page: Savings, dated: false },
  { divider: true },
  { label: 'Categories', Page: Categories, dated: false },
  { label: 'Budget', Page: Settings, dated: false },
]

// Keeps a crashing page from unmounting the whole app; the nav stays usable.
class PageBoundary extends Component {
  state = { error: null }
  static getDerivedStateFromError(error) {
    return { error }
  }
  render() {
    if (this.state.error) {
      return <p className="notice">This page stopped working: {this.state.error.message}</p>
    }
    return this.props.children
  }
}

function Shell({ user, onSignOut }) {
  const [tab, setTab] = useState('Overview')
  const active = TABS.find((t) => t.label === tab)
  const { Page } = active

  return (
    <div className="shell">
      <nav className="rail">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">₹</span>
          LodgeLedger
        </div>
        <div className="rail-nav">
          {TABS.map(({ label, divider }, i) =>
            divider ? (
              <hr className="rail-divider" key={`divider-${i}`} />
            ) : (
              <button
                key={label}
                className={label === tab ? 'rail-tab is-active' : 'rail-tab'}
                aria-current={label === tab ? 'page' : undefined}
                onClick={() => setTab(label)}
              >
                {label}
              </button>
            ),
          )}
        </div>
        <div className="rail-foot">
          <p className="rail-user" title={user.email}>
            Signed in as <strong>{user.name}</strong>
          </p>
          <div className="rail-actions">
            <ThemeToggle />
            <button type="button" className="theme-toggle" onClick={onSignOut}>Sign out</button>
          </div>
        </div>
      </nav>

      <main className="view">
        <header className="view-head">
          {active.dated && <p className="eyebrow">Today · {todayLabel()}</p>}
          <h1 className="view-title">{tab}</h1>
        </header>
        <PageBoundary key={tab}>
          <Page />
        </PageBoundary>
      </main>
    </div>
  )
}

export default function App() {
  // undefined: still checking a stored session; null: signed out.
  const [user, setUser] = useState(() => (getToken() ? undefined : null))
  const [bootError, setBootError] = useState('')

  const checkSession = () => {
    setBootError('')
    getMe()
      .then(setUser)
      .catch((err) => (err.status === 401 ? setUser(null) : setBootError(err.message)))
  }

  useEffect(() => {
    // Any page that gets a 401 (expired or revoked session) lands here.
    const stop = onLoggedOut(() => setUser(null))
    if (getToken()) checkSession()
    return stop
  }, [])

  const signOut = async () => {
    await logout()
    setUser(null)
  }

  if (bootError) {
    return (
      <div className="auth-shell">
        <p className="notice" role="alert">
          {bootError} <button className="btn-link" onClick={checkSession}>Try again</button>
        </p>
      </div>
    )
  }
  if (user === undefined) return <div className="auth-shell"><p className="empty">Loading…</p></div>
  if (user === null) return <AuthPage onSignedIn={setUser} />
  // Keyed by account: switching users remounts every page, so nothing from the
  // previous account's screens can linger.
  return <Shell key={user.id} user={user} onSignOut={signOut} />
}
