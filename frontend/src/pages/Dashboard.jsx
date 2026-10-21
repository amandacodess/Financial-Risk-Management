import { useCallback, useEffect, useState } from 'react'
import { getSummary } from '../api'
import { currentMonth, money, moneyRound, signedMoney, percent, monthLabel } from '../format'
import { useCountUp } from '../useCountUp'

// Bars are scaled to the largest category so they can be compared by length,
// which loses the one thing length cannot show: what share of the month this
// was. Hovering a row names it.
function Bar({ label, value, max, total, forecast }) {
  const pct = max > 0 ? Math.min(100, (value / max) * 100) : 0
  return (
    <div className="bar-row">
      <div className="bar-label">{label}</div>
      <div className="bar-track">
        <div className={forecast ? 'bar-fill is-forecast' : 'bar-fill'} style={{ width: `${pct}%` }} />
      </div>
      <div className="bar-value">
        {total > 0 && <span className="bar-share">{percent((value / total) * 100)}</span>}
        {money(value)}
      </div>
    </div>
  )
}

const STATUS_FILL = { ok: 'bar-fill is-ok', warning: 'bar-fill is-warning', exceeded: 'bar-fill is-over' }
const STATUS_WORD = { ok: 'within budget', warning: 'near limit', exceeded: 'over budget' }

// "100.0%" would read as on budget for a category ₹0.01 over, so anything
// over its budget never shows less than ">100%".
const usedLabel = (line) =>
  line.status === 'exceeded' && line.utilization_pct <= 100 ? '>100%' : `${line.utilization_pct.toFixed(1)}%`

// A budgeted category against its own limit: the bar is the share of the
// budget used, coloured by the same status the risk rules use.
function BudgetBar({ line }) {
  const width = Math.min(100, line.utilization_pct)
  return (
    <div className="budget-line">
      <div className="bar-row">
        <div className="bar-label">{line.category}</div>
        <div className="bar-track" role="img"
          aria-label={`${line.category}: ${usedLabel(line)} of budget, ${STATUS_WORD[line.status]}`}>
          <div className={STATUS_FILL[line.status]} style={{ width: `${width}%` }} />
        </div>
        <div className={line.status === 'ok' ? 'bar-value' : `bar-value is-${line.status}`}>
          {usedLabel(line)}
        </div>
      </div>
      <p className="budget-detail">
        {money(line.spent)} of {money(line.budget)} ·{' '}
        {line.remaining >= 0 ? `${money(line.remaining)} left` : `${money(-line.remaining)} over`}
      </p>
    </div>
  )
}

// One axis carries both the money and the verdict: solid is what you have spent,
// hatched is where this month's rate lands you, and the rule is the budget.
function PaceTrack({ summary }) {
  const budget = summary.budget_total
  const spent = summary.expenses
  const { projected_expenses: projected, days_elapsed: day, days_in_month: days } = summary.pace
  const hasBudget = budget > 0
  const over = hasBudget && projected > budget
  const finished = day === days
  const counted = useCountUp(spent)

  // Scaling to the largest of the three keeps an overshoot on screen instead of
  // clipping it at the end of the track.
  const scale = Math.max(budget, projected, spent, 1)
  const pct = (n) => `${(n / scale) * 100}%`
  const budgetAt = (budget / scale) * 100

  return (
    <div className="pace">
      {/* Rounded: paise are noise on a figure set this large. */}
      <span className={over ? 'pace-amount is-over' : 'pace-amount'}>{moneyRound(counted)}</span>
      <p className="pace-caption">
        spent {finished ? 'in the month' : `so far · day ${day} of ${days}`}
      </p>

      <div className="pace-track">
        <div className="pace-spent" style={{ width: pct(spent) }} />
        <div
          className={over ? 'pace-projected is-over' : 'pace-projected'}
          style={{ left: pct(spent), width: pct(Math.max(0, projected - spent)) }}
        />
        {hasBudget && (
          <div className={over ? 'pace-budget is-crossed' : 'pace-budget'} style={{ left: pct(budget) }}>
            {/* The label hangs off whichever side of the line has room. */}
            <span className={budgetAt > 50 ? 'pace-budget-label is-left' : 'pace-budget-label'}>
              budgets {moneyRound(budget)}
            </span>
          </div>
        )}
      </div>

      <p className={over ? 'pace-verdict is-over' : 'pace-verdict'}>
        {!hasBudget ? (
          <>Set category budgets under Budget to see whether this pace lands inside them.</>
        ) : finished ? (
          over ? (
            <>The month closed at <strong>{moneyRound(spent)}</strong> —{' '}
              <strong>{moneyRound(spent - budget)} over</strong> the {moneyRound(budget)} budgeted.</>
          ) : (
            <>The month closed at <strong>{moneyRound(spent)}</strong>,{' '}
              <strong>{moneyRound(budget - spent)}</strong> inside the {moneyRound(budget)} budgeted.</>
          )
        ) : over ? (
          <>
            At this rate you finish the month at <strong>{moneyRound(projected)}</strong> —{' '}
            <strong>{moneyRound(projected - budget)} over</strong> your budgets.
          </>
        ) : (
          <>
            At this rate you finish the month at <strong>{moneyRound(projected)}</strong>, leaving{' '}
            <strong>{moneyRound(budget - projected)}</strong> of your budgets unspent.
          </>
        )}
      </p>
    </div>
  )
}

// The backend's risk engine decides what is flagged; this only presents it.
function Risks({ risks }) {
  return (
    <div className="panel is-wide">
      <h2 className="panel-title">Risk alerts</h2>
      {risks.length === 0 ? (
        <p className="empty">Nothing flagged for this month under the current rules.</p>
      ) : (
        <ul className="risk-list">
          {risks.map((r, i) => (
            <li key={`${r.code}-${r.category_id ?? i}`} className={`risk is-${r.severity}`}>
              <span className={`tag is-${r.severity}`}>{r.severity === 'critical' ? 'Critical' : 'Warning'}</span>
              <span>{r.message}</span>
            </li>
          ))}
        </ul>
      )}
      <p className="confirm">
        Illustrative rules, not financial advice: a warning at 80% of a category budget, a flag
        above 100%, and a flag when expenses exceed income.
      </p>
    </div>
  )
}

export default function Dashboard() {
  const [month, setMonth] = useState(currentMonth)
  const [summary, setSummary] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = useCallback(() => {
    setLoading(true)
    setError('')
    // Cleared first: the previous month's totals must never sit under a new month.
    setSummary(null)
    getSummary(month)
      .then(setSummary)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [month])

  useEffect(() => { load() }, [load])

  const picker = (
    <div className="panel-head view-tools">
      <label className="field">
        <span className="field-label">Showing</span>
        <input type="month" value={month} onChange={(e) => e.target.value && setMonth(e.target.value)} />
      </label>
      {summary && !loading && <p className="empty">{monthLabel(summary.month)}</p>}
      {loading && <p className="empty" role="status">Loading…</p>}
    </div>
  )

  if (error) {
    return (
      <div>
        {picker}
        <p className="notice" role="alert">
          {error} <button className="btn-link" onClick={load}>Try again</button>
        </p>
      </div>
    )
  }
  if (!summary) return picker

  const s = summary
  const spending = s.categories.filter((c) => c.spent > 0)
  const budgeted = s.categories.filter((c) => c.budget !== null)
  const spendMax = Math.max(1, ...spending.map((c) => c.spent))
  const forecastMax = Math.max(1, ...s.forecast.map((f) => f.predicted))
  const forecastTotal = s.forecast.reduce((sum, f) => sum + f.predicted, 0)

  // What happened and what is coming sit side by side: read as a pair, the two
  // category lists answer "is next month going to look like this one?".
  return (
    <div>
      {picker}
      <div className="grid">
        <div className="panel is-hero is-wide">
          <PaceTrack summary={s} />
        </div>

        <div className="panel is-wide">
          <h2 className="panel-title">The month in figures</h2>
          <div className="figures">
            <div className="figure">
              <span className="figure-value">{moneyRound(s.income)}</span>
              <p className="figure-label">Income</p>
            </div>
            <div className="figure">
              <span className="figure-value">{moneyRound(s.expenses)}</span>
              <p className="figure-label">Expenses</p>
            </div>
            <div className="figure">
              <span className={s.net_cash_flow < 0 ? 'figure-value is-over' : 'figure-value is-keep'}>
                {signedMoney(s.net_cash_flow)}
              </span>
              <p className="figure-label">Net cash flow</p>
            </div>
            <div className="figure">
              <span className={s.net_cash_flow < 0 ? 'figure-value is-over' : 'figure-value'}>
                {s.savings_rate_pct === null ? '—' : percent(s.savings_rate_pct)}
              </span>
              <p className="figure-label">Savings rate</p>
            </div>
          </div>
          <p className="confirm">
            Net cash flow is income minus expenses recorded for this month — not a bank balance.
            {s.savings_rate_pct === null && ' The savings rate needs some income to be measured against.'}
          </p>
        </div>

        <Risks risks={s.risks} />

        <div className="panel">
          <h2 className="panel-title">Budget vs actual</h2>
          {budgeted.length === 0 ? (
            <p className="empty">No budgets for this month. Add them under Budget.</p>
          ) : (
            budgeted.map((line) => <BudgetBar key={line.category_id} line={line} />)
          )}
        </div>

        <div className="panel">
          <h2 className="panel-title">Where it went</h2>
          {spending.length === 0 ? (
            <p className="empty">Nothing recorded this month. Add an entry under Expenses.</p>
          ) : (
            spending.map((c) => (
              <Bar key={c.category_id} label={c.category} value={c.spent} max={spendMax} total={s.expenses} />
            ))
          )}
        </div>

        <div className="panel is-wide">
          <h2 className="panel-title">Expected this month, if the three before repeat</h2>
          {s.forecast.length === 0 ? (
            <p className="empty">
              No spending in the three months before this one. The forecast appears once there is history.
            </p>
          ) : (
            s.forecast.map((f) => (
              <Bar
                key={f.category_id} label={f.category} value={f.predicted}
                max={forecastMax} total={forecastTotal} forecast
              />
            ))
          )}
        </div>
      </div>
    </div>
  )
}
