import { useCallback, useEffect, useState } from 'react'
import { getPrediction, getExpenses, getCategories, getSavings, getInsight } from '../api'
import { currentMonth, money, moneyRound, signedMoney, percent } from '../format'
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

// One axis carries both the money and the verdict: solid is what you have spent,
// hatched is where this month's rate lands you, and the rule is the budget.
function PaceTrack({ alert }) {
  const { monthly_budget: budget, spent_so_far: spent, projected_total: projected } = alert
  const hasBudget = budget > 0
  const counted = useCountUp(spent)

  // Scaling to the largest of the three keeps an overshoot on screen instead of
  // clipping it at the end of the track.
  const scale = Math.max(budget, projected, spent, 1)
  const pct = (n) => `${(n / scale) * 100}%`

  const budgetAt = (budget / scale) * 100
  const remaining = budget - projected

  return (
    <div className="pace">
      {/* Rounded: paise are noise on a figure set this large. */}
      <span className={alert.over_budget ? 'pace-amount is-over' : 'pace-amount'}>
        {moneyRound(counted)}
      </span>
      <p className="pace-caption">
        spent so far · day {alert.days_elapsed} of {alert.days_in_month}
      </p>

      <div className="pace-track">
        <div className="pace-spent" style={{ width: pct(spent) }} />
        <div
          className={alert.over_budget ? 'pace-projected is-over' : 'pace-projected'}
          style={{ left: pct(spent), width: pct(Math.max(0, projected - spent)) }}
        />
        {hasBudget && (
          <div
            className={alert.over_budget ? 'pace-budget is-crossed' : 'pace-budget'}
            style={{ left: pct(budget) }}
          >
            {/* The label hangs off whichever side of the line has room. */}
            <span className={budgetAt > 50 ? 'pace-budget-label is-left' : 'pace-budget-label'}>
              budget {moneyRound(budget)}
            </span>
          </div>
        )}
      </div>

      <p className={alert.over_budget ? 'pace-verdict is-over' : 'pace-verdict'}>
        {!hasBudget ? (
          <>Set a monthly budget to see whether this pace lands inside it.</>
        ) : alert.over_budget ? (
          <>
            At this rate you finish the month at <strong>{moneyRound(projected)}</strong> —{' '}
            <strong>{moneyRound(alert.projected_overage)} over</strong> budget.
          </>
        ) : (
          <>
            At this rate you finish the month at <strong>{moneyRound(projected)}</strong>, leaving{' '}
            <strong>{moneyRound(remaining)}</strong> of your budget unspent.
          </>
        )}
      </p>
    </div>
  )
}

// The written analysis, set as an annotation on the books rather than a card:
// a hanging bracket in the margin and the reviewer's hand in italic.
function Analysis() {
  const [insight, setInsight] = useState(null)
  const [busy, setBusy] = useState(true)

  const load = useCallback((refresh) => {
    setBusy(true)
    getInsight(refresh)
      .then(setInsight)
      .catch((err) => setInsight({ available: false, reason: err.message }))
      .finally(() => setBusy(false))
  }, [])

  useEffect(() => { load(false) }, [load])

  return (
    <div className="panel is-wide">
      <div className="panel-head">
        <h2 className="panel-title">The analysis</h2>
        {insight?.available && (
          <button className="btn-link" onClick={() => load(true)} disabled={busy}>
            Read again
          </button>
        )}
      </div>

      {busy && <p className="empty">Reading the books…</p>}

      {!busy && insight && !insight.available && <p className="empty">{insight.reason}</p>}

      {!busy && insight?.available && (
        <>
          {insight.text.split(/\n\s*\n/).map((paragraph, i) => (
            <p className="margin-note" key={i}>{paragraph}</p>
          ))}
          <p className="attribution">
            Reviewed by {insight.model} ·{' '}
            {new Date(insight.generated_at).toLocaleString(undefined, {
              day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit',
            })}
          </p>
        </>
      )}
    </div>
  )
}

export default function Dashboard() {
  const [prediction, setPrediction] = useState(null)
  const [savings, setSavings] = useState(null)
  const [currentSpend, setCurrentSpend] = useState([])
  const [error, setError] = useState('')

  useEffect(() => {
    Promise.all([getPrediction(), getExpenses(currentMonth()), getCategories(), getSavings()])
      .then(([pred, expenses, categories, saved]) => {
        setPrediction(pred)
        setSavings(saved)

        const nameById = Object.fromEntries(categories.map((c) => [c.id, c.name]))
        const totals = {}
        for (const e of expenses) {
          const name = nameById[e.category_id] || 'Unknown'
          totals[name] = (totals[name] || 0) + e.amount
        }
        setCurrentSpend(
          Object.entries(totals)
            .map(([category, amount]) => ({ category, amount }))
            .sort((a, b) => b.amount - a.amount),
        )
      })
      .catch((err) => setError(err.message))
  }, [])

  if (error) return <p className="notice">{error}</p>
  if (!prediction || !savings) return <p className="empty">Loading…</p>

  const { budget_alert: alert, forecast } = prediction
  const spendMax = Math.max(1, ...currentSpend.map((s) => s.amount))
  const spendTotal = currentSpend.reduce((sum, s) => sum + s.amount, 0)
  const forecastMax = Math.max(1, ...forecast.map((f) => f.predicted_amount))
  const forecastTotal = forecast.reduce((sum, f) => sum + f.predicted_amount, 0)
  const kept = savings.current

  // What happened and what is coming sit side by side: read as a pair, the two
  // category lists answer "is next month going to look like this one?".
  return (
    <div className="grid">
      <div className="panel is-hero is-wide">
        <PaceTrack alert={alert} />
      </div>

      <div className="panel is-wide">
        <h2 className="panel-title">What you kept</h2>
        <div className="figures">
          <div className="figure">
            <span className={kept.net < 0 ? 'figure-value is-over' : 'figure-value is-keep'}>
              {signedMoney(kept.net)}
            </span>
            <p className="figure-label">This month</p>
          </div>
          <div className="figure">
            <span className={kept.net < 0 ? 'figure-value is-over' : 'figure-value'}>
              {kept.income > 0 ? percent(kept.rate) : '—'}
            </span>
            <p className="figure-label">Savings rate</p>
          </div>
          <div className="figure">
            <span className="figure-value is-keep">{moneyRound(savings.total_saved)}</span>
            <p className="figure-label">Put aside so far</p>
          </div>
          <div className="figure">
            <span className="figure-value">{savings.goals.length}</span>
            <p className="figure-label">
              {savings.goals.length === 1 ? 'Goal running' : 'Goals running'}
            </p>
          </div>
        </div>
      </div>

      <div className="panel">
        <h2 className="panel-title">Where it went</h2>
        {currentSpend.length === 0 ? (
          <p className="empty">Nothing recorded this month yet. Add an entry under Expenses.</p>
        ) : (
          currentSpend.map((s) => (
            <Bar
              key={s.category} label={s.category} value={s.amount}
              max={spendMax} total={spendTotal}
            />
          ))
        )}
      </div>

      <div className="panel">
        <h2 className="panel-title">Next month, if the last three repeat</h2>
        {forecast.length === 0 ? (
          <p className="empty">
            No completed months on record yet. The forecast appears once you have history.
          </p>
        ) : (
          forecast.map((f) => (
            <Bar
              key={f.category} label={f.category} value={f.predicted_amount}
              max={forecastMax} total={forecastTotal} forecast
            />
          ))
        )}
      </div>

      <Analysis />
    </div>
  )
}
