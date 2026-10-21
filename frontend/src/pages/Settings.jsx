import { useCallback, useEffect, useState } from 'react'
import {
  getBudgets, createBudget, updateBudget, deleteBudget, getCategories, getSettings, updateSettings,
} from '../api'
import { currentMonth, money, monthLabel } from '../format'

const AMOUNT = /^\d+(\.\d{1,2})?$/
const validAmount = (value, allowZero = false) =>
  AMOUNT.test(value.trim()) && (allowZero ? Number(value) >= 0 : Number(value) > 0)

// One budget per expense category per month. Overview compares each against
// what was actually spent and raises the risk flags.
function MonthlyBudgets() {
  const [month, setMonth] = useState(currentMonth)
  const [budgets, setBudgets] = useState([])
  const [categories, setCategories] = useState([])
  const [loading, setLoading] = useState(true)
  const [form, setForm] = useState({ category_id: '', amount: '' })
  const [editing, setEditing] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [saved, setSaved] = useState('')

  const load = useCallback(() => {
    setLoading(true)
    return Promise.all([getCategories('expense'), getBudgets(month)])
      .then(([cats, rows]) => {
        setCategories(cats)
        setBudgets(rows)
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [month])

  useEffect(() => { load() }, [load])

  const reset = () => {
    setEditing(null)
    setForm({ category_id: '', amount: '' })
  }

  const submit = async (e) => {
    e.preventDefault()
    setError('')
    setSaved('')
    if (!editing && !form.category_id) return setError('Choose a category.')
    if (!validAmount(form.amount)) return setError('Enter a budget greater than 0, with at most two decimals.')
    setBusy(true)
    try {
      if (editing) {
        await updateBudget(editing.id, form.amount.trim())
        setSaved(`${editing.category} budget updated.`)
      } else {
        const created = await createBudget({
          category_id: Number(form.category_id), month, amount: form.amount.trim(),
        })
        setSaved(`${created.category} budget set for ${monthLabel(month)}.`)
      }
      reset()
      await load()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const remove = async (budget) => {
    if (!confirm(`Remove the ${budget.category} budget for ${monthLabel(month)}?`)) return
    setError('')
    setSaved('')
    try {
      await deleteBudget(budget.id)
      if (editing?.id === budget.id) reset()
      setSaved(`${budget.category} budget removed.`)
      await load()
    } catch (err) {
      setError(err.message)
    }
  }

  const total = budgets.reduce((sum, b) => sum + b.amount, 0)

  return (
    <div className="panel">
      <div className="panel-head">
        <h2 className="panel-title">Monthly budgets</h2>
        <label className="field">
          <span className="field-label">Month</span>
          <input type="month" value={month}
            onChange={(e) => { if (e.target.value) { setMonth(e.target.value); reset() } }} />
        </label>
      </div>

      <form onSubmit={submit} className="controls" noValidate>
        <label className="field">
          <span className="field-label">Category</span>
          <select value={editing ? editing.category_id : form.category_id} disabled={!!editing}
            onChange={(e) => setForm({ ...form, category_id: e.target.value })}>
            <option value="">Choose…</option>
            {categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </label>
        <label className="field">
          <span className="field-label">Budget (₹)</span>
          <input type="number" inputMode="decimal" step="0.01" min="0.01" placeholder="0.00" size="10"
            value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} />
        </label>
        <button type="submit" className="btn" disabled={busy}>
          {busy ? 'Saving…' : editing ? 'Save budget' : 'Add budget'}
        </button>
        {editing && <button type="button" className="btn-quiet" onClick={reset}>Cancel</button>}
      </form>
      {error && <p className="notice" role="alert">{error}</p>}
      {saved && <p className="confirm is-success" role="status">{saved}</p>}

      <div className="table-scroll" style={{ marginTop: '1.25rem' }}>
        <table className="table">
          <thead>
            <tr>
              <th>Category</th>
              <th className="col-amount">Budget</th>
              <th className="col-actions"><span className="sr-only">Actions</span></th>
            </tr>
          </thead>
          <tbody>
            {budgets.map((b) => (
              <tr key={b.id}>
                <td>{b.category}</td>
                <td className="cell-num col-amount">{money(b.amount)}</td>
                <td className="col-actions">
                  <span className="row-actions">
                    <button className="btn-link" onClick={() => {
                      setError(''); setSaved('')
                      setEditing(b); setForm({ category_id: String(b.category_id), amount: b.amount.toFixed(2) })
                    }}>Edit</button>
                    <button className="btn-link is-danger" onClick={() => remove(b)}>Delete</button>
                  </span>
                </td>
              </tr>
            ))}
            {budgets.length === 0 && (
              <tr>
                <td colSpan="3">
                  <p className="empty">
                    {loading ? 'Loading…' : `No budgets for ${monthLabel(month)}. Add one above and Overview will track it.`}
                  </p>
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      {budgets.length > 0 && (
        <p className="confirm">Total budgeted for {monthLabel(month)}: {money(total)}</p>
      )}
    </div>
  )
}

function SavingsTarget() {
  const [amount, setAmount] = useState('')
  const [loaded, setLoaded] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [saved, setSaved] = useState('')

  useEffect(() => {
    getSettings()
      .then((s) => { setAmount(s.savings_target.toFixed(2)); setLoaded(true) })
      .catch((err) => setError(err.message))
  }, [])

  const submit = async (e) => {
    e.preventDefault()
    setError('')
    setSaved('')
    if (!validAmount(amount, true)) return setError('Enter 0 or more, with at most two decimals.')
    setBusy(true)
    try {
      const s = await updateSettings({ savings_target: amount.trim() })
      setSaved(s.savings_target > 0
        ? `Target set to ${money(s.savings_target)} a month. Savings will tell you how close you are.`
        : 'Target cleared. Savings will show what you kept without judging it.')
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="panel">
      <h2 className="panel-title">Monthly savings target</h2>
      <form onSubmit={submit} className="controls" noValidate>
        <label className="field">
          <span className="field-label">Amount (₹)</span>
          <input type="number" inputMode="decimal" step="0.01" min="0" size="10" disabled={!loaded}
            value={amount} onChange={(e) => { setAmount(e.target.value); setSaved('') }} />
        </label>
        <button type="submit" className="btn" disabled={busy || !loaded}>{busy ? 'Saving…' : 'Save'}</button>
      </form>
      {error && <p className="notice" role="alert">{error}</p>}
      {saved && <p className="confirm is-success" role="status">{saved}</p>}
    </div>
  )
}

export default function Settings() {
  return (
    <div>
      <MonthlyBudgets />
      <SavingsTarget />
      <div className="panel">
        <h2 className="panel-title">Where your data lives</h2>
        <p className="confirm" style={{ marginTop: 0 }}>
          Your entries are stored in a Supabase PostgreSQL database under your account, reached
          only through the LodgeLedger API. Other accounts cannot see them. This page never holds
          a database password or key.
        </p>
        <p className="confirm">
          Risk flags on Overview are simple illustrative rules (a warning at 80% of a budget,
          a flag above 100%, and spending more than came in), not financial advice.
        </p>
      </div>
    </div>
  )
}
