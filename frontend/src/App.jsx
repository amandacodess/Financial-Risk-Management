import { Component, useState } from 'react'
import Dashboard from './pages/Dashboard'
import Expenses from './pages/Expenses'
import Income from './pages/Income'
import Savings from './pages/Savings'
import Categories from './pages/Categories'
import Settings from './pages/Settings'
import { monthLabel } from './format'

// "Budget" rather than "Settings": the page holds what you set, so name it after
// that. Month-scoped pages carry the month as an eyebrow. The divider separates
// what you record daily from what you set up once.
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

// null means "follow the system"; a stored value means the reader chose.
const storedTheme = () => {
  try {
    return localStorage.getItem('ledger-theme')
  } catch {
    return null
  }
}

function ThemeToggle() {
  const [theme, setTheme] = useState(storedTheme)

  const choose = (next) => {
    setTheme(next)
    document.documentElement.dataset.theme = next
    try {
      localStorage.setItem('ledger-theme', next)
    } catch {
      // Private browsing refuses storage; the choice just will not persist.
    }
  }

  // Whichever palette is not showing is the one worth offering. Without a
  // stored choice, read what the system actually resolved to.
  const isDark =
    theme === 'dark' ||
    (!theme && window.matchMedia?.('(prefers-color-scheme: dark)').matches)

  return (
    <button className="theme-toggle" onClick={() => choose(isDark ? 'light' : 'dark')}>
      {isDark ? 'Day ledger' : 'Night ledger'}
    </button>
  )
}

export default function App() {
  const [tab, setTab] = useState('Overview')
  const active = TABS.find((t) => t.label === tab)
  const { Page } = active

  return (
    <div className="shell">
      <nav className="rail">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">₹</span>
          Ledger
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
          <ThemeToggle />
        </div>
      </nav>

      <main className="view">
        <header className="view-head">
          {active.dated && <p className="eyebrow">{monthLabel()}</p>}
          <h1 className="view-title">{tab}</h1>
        </header>
        <PageBoundary key={tab}>
          <Page />
        </PageBoundary>
      </main>
    </div>
  )
}
