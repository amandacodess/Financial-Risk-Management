import { useCallback, useEffect, useState } from 'react'
import { getExpenses, createExpense, updateExpense, deleteExpense, getCategories } from '../api'
import { today, currentMonth, dayLabel, money } from '../format'

// A function, not a const: a module-level date goes stale once the app is left
// open past midnight.
const emptyForm = () => ({ amount: '', category_id: '', date: today(), note: '' })

export default function Expenses() {
  const [month, setMonth] = useState(currentMonth)
  const [expenses, setExpenses] = useState([])
  const [categories, setCategories] = useState([])
  const [form, setForm] = useState(emptyForm)
  const [busy, setBusy] = useState(false)
  const [editingId, setEditingId] = useState(null)
  const [error, setError] = useState('')

  const load = useCallback(() => {
    getCategories().then(setCategories).catch((err) => setError(err.message))
    getExpenses(month).then(setExpenses).catch((err) => setError(err.message))
  }, [month])

  useEffect(() => { load() }, [load])

  const categoryName = (id) => categories.find((c) => c.id === id)?.name || 'Unknown'
  const total = expenses.reduce((sum, e) => sum + e.amount, 0)

  const submit = async (e) => {
    e.preventDefault()
    setError('')
    const payload = {
      amount: parseFloat(form.amount),
      category_id: parseInt(form.category_id, 10),
      date: form.date,
      note: form.note,
    }
    setBusy(true)
    try {
      if (editingId) {
        await updateExpense(editingId, payload)
      } else {
        await createExpense(payload)
      }
      setForm(emptyForm())
      setEditingId(null)
      // Follow the expense to its own month, otherwise saving one outside the
      // current filter looks like nothing happened.
      const saved = payload.date.slice(0, 7)
      if (saved !== month) setMonth(saved)
      else load()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const startEdit = (expense) => {
    setEditingId(expense.id)
    setForm({
      amount: String(expense.amount),
      category_id: String(expense.category_id),
      date: expense.date,
      note: expense.note || '',
    })
  }

  const remove = async (id) => {
    if (!confirm('Delete this expense? This cannot be undone.')) return
    setError('')
    try {
      await deleteExpense(id)
      load()
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <div>
      <div className="panel">
        <h2 className="panel-title">{editingId ? 'Edit entry' : 'New entry'}</h2>
        <form onSubmit={submit}>
          <div className="controls">
            <label className="field">
              <span className="field-label">Amount</span>
              <input
                type="number" step="0.01" min="0.01" placeholder="0.00" required size="8"
                value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })}
              />
            </label>
            <label className="field">
              <span className="field-label">Category</span>
              <select
                required value={form.category_id}
                onChange={(e) => setForm({ ...form, category_id: e.target.value })}
              >
                <option value="">Choose…</option>
                {categories.map((c) => (
                  <option key={c.id} value={c.id}>{c.name}</option>
                ))}
              </select>
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
                type="text" placeholder="What was it for?"
                value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })}
              />
            </label>
            <button type="submit" className="btn" disabled={busy}>
              {editingId ? 'Save changes' : 'Add entry'}
            </button>
            {editingId && (
              <button
                type="button" className="btn-quiet"
                onClick={() => { setEditingId(null); setForm(emptyForm()) }}
              >
                Cancel
              </button>
            )}
          </div>
        </form>
        {error && <p className="notice">{error}</p>}
      </div>

      <div className="panel">
        <div className="controls" style={{ justifyContent: 'space-between', marginBottom: '1.25rem' }}>
          <label className="field">
            <span className="field-label">Showing</span>
            <input type="month" value={month} onChange={(e) => setMonth(e.target.value)} />
          </label>
          <p className="empty">
            {expenses.length} {expenses.length === 1 ? 'entry' : 'entries'} · {money(total)}
          </p>
        </div>

        <div className="table-scroll">
        <table className="table">
          <thead>
            <tr>
              <th>Date</th>
              <th>Category</th>
              <th className="col-amount">Amount</th>
              <th className="col-note">Note</th>
              <th className="col-actions"><span className="sr-only">Actions</span></th>
            </tr>
          </thead>
          <tbody>
            {expenses.map((e) => (
              <tr key={e.id}>
                <td className="cell-num cell-muted">{dayLabel(e.date)}</td>
                <td>{categoryName(e.category_id)}</td>
                <td className="cell-num col-amount">{money(e.amount)}</td>
                <td className="cell-muted col-note">{e.note}</td>
                <td className="col-actions">
                  <span className="row-actions">
                    <button className="btn-link" onClick={() => startEdit(e)}>Edit</button>
                    <button className="btn-link is-danger" onClick={() => remove(e.id)}>Delete</button>
                  </span>
                </td>
              </tr>
            ))}
            {expenses.length === 0 && (
              <tr>
                <td colSpan="5"><p className="empty">Nothing recorded for this month.</p></td>
              </tr>
            )}
          </tbody>
        </table>
        </div>
      </div>
    </div>
  )
}
