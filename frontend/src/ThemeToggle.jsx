import { useState } from 'react'

// Also read in index.html before first paint, so the page never flashes the
// wrong palette. null means "follow the system"; a stored value means the reader chose.
export const THEME_KEY = 'lodgeledger-theme'

const storedTheme = () => {
  try {
    return localStorage.getItem(THEME_KEY)
  } catch {
    return null
  }
}

export default function ThemeToggle() {
  const [theme, setTheme] = useState(storedTheme)

  const choose = (next) => {
    setTheme(next)
    document.documentElement.dataset.theme = next
    try {
      localStorage.setItem(THEME_KEY, next)
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
    <button
      type="button"
      className="theme-toggle"
      aria-label={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
      onClick={() => choose(isDark ? 'light' : 'dark')}
    >
      <span aria-hidden="true">{isDark ? '☀' : '☾'}</span> {isDark ? 'Light mode' : 'Dark mode'}
    </button>
  )
}
