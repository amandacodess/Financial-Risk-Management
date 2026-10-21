import { useCallback, useEffect, useState } from 'react'
import { getMonthly, getGoals, getSettings, createGoal, deleteGoal, addContribution } from '../api'
import {
  today, money, moneyRound, signedMoney, percent, monthShort, monthLabel, dayLabel,
} from '../format'

const emptyGoal = () => ({ name: '', target_amount: '', target_date: '' })

// What each pace state is called, and what it tells you to do about it.
function paceCopy(goal) {
  const { pace, required_per_month: required, observed_per_month: observed } = goal
  switch (pace) {
    case 'complete':
      return { tag: 'Funded', line: 'Target reached.' }
    case 'ahead':
      return {
        tag: 'On pace',
        line: `Putting aside ${moneyRound(observed)} a month, and ${moneyRound(required)} would do it.`,
      }
    case 'behind':
      return {
        tag: 'Behind',
        line:
          goal.months_left === 0
            ? `${moneyRound(goal.remaining)} still to find, and the deadline is this month.`
            : `Needs ${moneyRound(required)} a month to land on time — currently ${moneyRound(observed)}.`,
      }
    case 'unknown':
      return {
        tag: 'Not started',
        line: `${moneyRound(required)} a month from now would land it by ${dayLabel(goal.target_date)}.`,
      }
    default:
      return { tag: 'No deadline', line: `${moneyRound(goal.remaining)} to go.` }
  }
}

// Six months of what you kept: above the line is money put aside, below it is a
// month that cost more than it brought in.
function SavingsHistory({ history }) {
  const scale = Math.max(1, ...history.map((m) => Math.abs(m.net)))

  return (
    <div className="spark">
      {history.map((m, i) => {
        const height = `${(Math.abs(m.net) / scale) * 100}%`
        const deficit = m.net < 0
        const isCurrent = i === history.length - 1
        return (
          <div key={m.month}>
            <div className="spark-col">
              <div className="spark-up">
                {!deficit && m.net > 0 && <div className="spark-bar" style={{ height }} />}
              </div>
              <div className="spark-down">
                {deficit && <div className="spark-bar is-deficit" style={{ height }} />}
              </div>
            </div>
            <p className={isCurrent ? 'spark-label is-current' : 'spark-label'}>
              {monthShort(m.month)}
              <span className="sr-only">
                {' '}— {monthLabel(m.month)}, kept {signedMoney(m.net)}
              </span>
            </p>
          </div>
        )
      })}
    </div>
  )
}

function Goal({ goal, onContribute, onDelete }) {
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState(() => ({ amount: '', date: today(), description: '' }))
  const [busy, setBusy] = useState(false)
  const { tag, line } = paceCopy(goal)

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true)
    try {
      await onContribute(goal.id, {
        amount: form.amount.trim(),
        date: form.date,
        description: form.description.trim(),
      })
      setForm({ amount: '', date: today(), description: '' })
      setOpen(false)
    } catch {
      // The page reports what went wrong; leave the form open and filled in
      // so the amount can be corrected rather than retyped.
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="goal">
      <div className="goal-head">
        <h3 className="goal-name">{goal.name}</h3>
        <span className="goal-figures">
          <strong>{money(goal.saved)}</strong> of {money(goal.target_amount)}
        </span>
      </div>

      <div className="goal-track">
        <div
          className={goal.pace === 'complete' ? 'goal-fill is-complete' : 'goal-fill'}
          style={{ width: `${goal.percent_complete}%` }}
        />
      </div>

      <div className="goal-meta">
        <span>
          <span className={`tag is-${goal.pace}`}>{tag}</span>{' '}
          <span style={{ marginLeft: '0.5rem' }}>{line}</span>
        </span>
        <span className="row-actions">
          <button className="btn-link is-keep" onClick={() => setOpen(!open)}>
            {open ? 'Cancel' : 'Add money'}
          </button>
          <button className="btn-link is-danger" onClick={() => onDelete(goal)}>Delete</button>
        </span>
      </div>

      {open && (
        <form onSubmit={submit} className="controls" style={{ marginTop: '1rem' }}>
          <label className="field">
            <span className="field-label">Amount</span>
            <input
              type="number" step="0.01" min="0.01" placeholder="0.00" required size="8" autoFocus
              value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })}
            />
          </label>
          <label className="field">
            <span className="field-label">Date</span>
            <input
              type="date" required
              value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })}
            />
          </label>
          <label className="field input-note">
            <span className="field-label">Note</span>
            <input
              type="text" placeholder="Where it came from"
              maxLength={200}
              value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })}
            />
          </label>
          <button type="submit" className="btn" disabled={busy}>{busy ? 'Saving…' : 'Add money'}</button>
        </form>
      )}
    </div>
  )
}

export default function Savings() {
  const [summary, setSummary] = useState(null)
  const [form, setForm] = useState(emptyGoal)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  // Six months of figures, the goals and the target, shaped into the one
  // summary this page was built around.
  const load = useCallback(() => {
    setError('')
    return Promise.all([getMonthly(6), getGoals(), getSettings()])
      .then(([monthly, goals, settings]) => {
        const history = monthly.months.map((m) => ({
          month: m.month, income: m.income, spent: m.expenses, net: m.net_cash_flow,
          rate: m.savings_rate_pct,
        }))
        setSummary({
          current: history[history.length - 1],
          history,
          average_rate: monthly.average_savings_rate_pct,
          target: settings.savings_target,
          goals,
          total_saved: goals.reduce((sum, g) => sum + g.saved, 0),
        })
      })
      .catch((err) => setError(err.message))
  }, [])

  useEffect(() => { load() }, [load])

  const submit = async (e) => {
    e.preventDefault()
    setError('')
    if (!form.name.trim()) return setError('Give the goal a name.')
    if (!/^\d+(\.\d{1,2})?$/.test(form.target_amount.trim()) || Number(form.target_amount) <= 0) {
      return setError('Enter a target greater than 0, with at most two decimals.')
    }
    setBusy(true)
    try {
      await createGoal({
        name: form.name.trim(),
        target_amount: form.target_amount.trim(),
        target_date: form.target_date || null,
      })
      setForm(emptyGoal())
      await load()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const contribute = async (goalId, contribution) => {
    setError('')
    try {
      await addContribution(goalId, contribution)
      await load()
    } catch (err) {
      setError(err.message)
      throw err
    }
  }

  const remove = async (goal) => {
    if (!confirm(`Delete "${goal.name}"? Everything recorded against it goes too.`)) return
    setError('')
    try {
      await deleteGoal(goal.id)
      await load()
    } catch (err) {
      setError(err.message)
    }
  }

  if (error && !summary) {
    return (
      <p className="notice" role="alert">
        {error} <button className="btn-link" onClick={load}>Try again</button>
      </p>
    )
  }
  if (!summary) return <p className="empty">Loading…</p>

  const { current, history, target, goals } = summary
  const hasIncome = current.income > 0
  const shortfall = target - current.net

  // Where you stand and how you got here, read as a pair.
  return (
    <div className="grid">
      <div className="panel">
        <h2 className="panel-title">This month</h2>
        <div className="figures">
          <div className="figure">
            <span className="figure-value">{moneyRound(current.income)}</span>
            <p className="figure-label">Came in</p>
          </div>
          <div className="figure">
            <span className="figure-value">{moneyRound(current.spent)}</span>
            <p className="figure-label">Went out</p>
          </div>
          <div className="figure">
            <span className={current.net < 0 ? 'figure-value is-over' : 'figure-value is-keep'}>
              {signedMoney(current.net)}
            </span>
            <p className="figure-label">Kept</p>
          </div>
          <div className="figure">
            <span className={current.net < 0 ? 'figure-value is-over' : 'figure-value'}>
              {hasIncome ? percent(current.rate) : '—'}
            </span>
            <p className="figure-label">Savings rate</p>
          </div>
        </div>

        <p className="pace-verdict" style={{ marginTop: '2rem' }}>
          {!hasIncome ? (
            <>Record what came in this month and this becomes a rate rather than a total.</>
          ) : target > 0 && current.net >= target ? (
            <>
              You have kept <strong>{moneyRound(current.net)}</strong> of the{' '}
              {moneyRound(current.income)} that came in — <strong>{moneyRound(-shortfall)} above</strong>{' '}
              your {moneyRound(target)} target.
            </>
          ) : target > 0 ? (
            <>
              You have kept <strong>{moneyRound(current.net)}</strong> so far, which is{' '}
              <strong>{moneyRound(shortfall)} short</strong> of your {moneyRound(target)} target.
            </>
          ) : (
            <>
              You have kept <strong>{moneyRound(current.net)}</strong> of the{' '}
              {moneyRound(current.income)} that came in. Set a monthly target under Budget to
              measure that against something.
            </>
          )}
        </p>
      </div>

      <div className="panel">
        <div className="panel-head">
          <h2 className="panel-title">Six months</h2>
          <p className="empty">
            Average rate {summary.average_rate ? percent(summary.average_rate) : '—'} · put aside{' '}
            {moneyRound(summary.total_saved)} across all goals
          </p>
        </div>
        <SavingsHistory history={history} />
      </div>

      <div className="panel is-wide">
        <h2 className="panel-title">Goals</h2>
        {goals.length === 0 ? (
          <p className="empty">
            No goals yet. Name one below and every amount you put towards it is tracked
            against the date you want it by.
          </p>
        ) : (
          goals.map((g) => (
            <Goal key={g.id} goal={g} onContribute={contribute} onDelete={remove} />
          ))
        )}
        {error && <p className="notice" role="alert">{error}</p>}
      </div>

      <div className="panel is-wide">
        <h2 className="panel-title">New goal</h2>
        <form onSubmit={submit} className="controls" noValidate>
          <label className="field input-note">
            <span className="field-label">Name</span>
            <input
              type="text" placeholder="Emergency fund, New laptop…" required
              value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })}
            />
          </label>
          <label className="field">
            <span className="field-label">Target</span>
            <input
              type="number" step="0.01" min="0.01" placeholder="0.00" required size="10"
              value={form.target_amount}
              onChange={(e) => setForm({ ...form, target_amount: e.target.value })}
            />
          </label>
          <label className="field">
            <span className="field-label">By (optional)</span>
            <input
              type="date"
              value={form.target_date}
              onChange={(e) => setForm({ ...form, target_date: e.target.value })}
            />
          </label>
          <button type="submit" className="btn" disabled={busy}>Add goal</button>
        </form>
        <p className="confirm">
          A goal without a date still tracks what you have put aside — it just has no pace
          to be behind on.
        </p>
      </div>
    </div>
  )
}
