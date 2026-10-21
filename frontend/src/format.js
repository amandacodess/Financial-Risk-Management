// Display formatting: dates and money. Everything the interface shows a person
// goes through here, so the ledger reads the same on every page.

// en-CA formats as YYYY-MM-DD in the user's own timezone. toISOString() would
// be UTC, which lands on the wrong day either side of midnight.
export const today = () => new Date().toLocaleDateString('en-CA')
export const currentMonth = () => today().slice(0, 7)

// Pinned, not the machine's locale: rupees group by lakh (₹1,23,456) and dates
// read day-first, neither of which a browser set to en-US would do.
const LOCALE = 'en-IN'

export const monthLabel = (month) => {
  // Day 15 avoids any timezone shift pushing the label into a neighbouring month.
  const d = month ? new Date(`${month}-15T00:00:00`) : new Date()
  return d.toLocaleDateString(LOCALE, { month: 'long', year: 'numeric' })
}

// Today in full ("21 October 2026"), for the page header.
export const todayLabel = () =>
  new Date().toLocaleDateString(LOCALE, { day: 'numeric', month: 'long', year: 'numeric' })

export const dayLabel = (date) =>
  new Date(`${date}T00:00:00`).toLocaleDateString(LOCALE, { day: 'numeric', month: 'short' })

const rupees = (digits) =>
  new Intl.NumberFormat(LOCALE, {
    style: 'currency',
    currency: 'INR',
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })

// Built once rather than per call: a long table formats every row through these.
const exact = rupees(2)
const rounded = rupees(0)

export const money = (n) => exact.format(n)
// Axis ticks and projections, where paise are noise.
export const moneyRound = (n) => rounded.format(n)

// A savings figure is worth reading as a direction, not just a size, so the
// plus is kept where most money formatting would drop it.
export const signedMoney = (n) => (n > 0 ? `+${moneyRound(n)}` : moneyRound(n))

export const percent = (n) => `${Math.round(n)}%`

// Compact axis label for the savings history strip.
export const monthShort = (month) =>
  new Date(`${month}-15T00:00:00`).toLocaleDateString(LOCALE, { month: 'short' })
