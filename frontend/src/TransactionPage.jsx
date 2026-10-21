import { useCallback, useEffect, useState } from 'react'
import { getTransactions, createTransaction, updateTransaction, deleteTransaction, getCategories } from './api'
import { today, currentMonth, dayLabel, money } from './format'

// A function, not a const: a module-level date goes stale once the app is left
// open past midnight.
const emptyForm = () => ({ amount: '', category_id: '', date: today(), description: '' })

// Mirrors the server's rule (positive, at most two decimals) so the common
// mistakes are caught before a round trip. The server still checks everything.
function validate(form) {
  if (!/^\d+(\.\d{1,2})?$/.test(form.amount.trim()) || Number(form.amount) <= 0) {
    return 'Enter an amount greater than 0, with at most two decimals.'
  }
  if (!form.category_id) return 'Choose a category.'
  if (!/^\d{4}-\d{2}-\d{2}$/.test(form.date)) return 'Enter a date.'
  return ''
}

// Expenses and Income are the same page over a different transaction type;
// `copy` carries the wording that tells them apart.
export default function TransactionPage({ type, copy }) {
  const [month, setMonth] = useState(currentMonth)
  const [entries, setEntries] = useState([])
  const [categories, setCategories] = useState([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')
  const [form, setForm] = useState(emptyForm)
  const [busy, setBusy] = useState(false)
  const [editingId, setEditingId] = useState(null)
  const [error, setError] = useState('')
  const [saved, setSaved] = useState('')
  const [attempt, setAttempt] = useState(0)

  // Categories once per visit: they do not change with the month. (Switching
  // pages remounts this one, so a category added on Categories still shows up.)
  useEffect(() => {
    getCategories(type).then(setCategories).catch((err) => setLoadError(err.message))
  }, [type, attempt])

  const load = useCallback(() => {
    setLoading(true)
    setLoadError('')
    return getTransactions({ month, type })
      .then(setEntries)
      .catch((err) => setLoadError(err.message))
      .finally(() => setLoading(false))
  }, [month, type])

  useEffect(() => { load() }, [load])

  const total = entries.reduce((sum, e) => sum + e.amount, 0)

  const resetForm = () => {
    setEditingId(null)
    setForm(emptyForm())
  }

  const submit = async (e) => {
    e.preventDefault()
    setError('')
    setSaved('')
    const problem = validate(form)
    if (problem) {
      setError(problem)
      return
    }
    const payload = {
      type,
      // Sent as a string so the server reads exactly what was typed (no float rounding).
      amount: form.amount.trim(),
      category_id: Number(form.category_id),
      date: form.date,
      description: form.description.trim(),
    }
    setBusy(true)
    try {
      if (editingId) {
        await updateTransaction(editingId, payload)
      } else {
        await createTransaction(payload)
      }
      setSaved(editingId ? 'Changes saved.' : 'Entry added.')
      resetForm()
      // Follow the entry to its own month, otherwise saving one outside the
      // current filter looks like nothing happened.
      const savedMonth = payload.date.slice(0, 7)
      if (savedMonth !== month) setMonth(savedMonth)
      else await load()
    } catch (err) {
      // The form keeps what was typed so it can be corrected, not retyped.
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const startEdit = (entry) => {
    setError('')
    setSaved('')
    setEditingId(entry.id)
    setForm({
      amount: entry.amount.toFixed(2),
      category_id: String(entry.category_id),
      date: entry.date,
      description: entry.description || '',
    })
  }

  const remove = async (entry) => {
    if (!confirm(`Delete this ${copy.noun}? This cannot be undone.`)) return
    setError('')
    setSaved('')
    try {
      await deleteTransaction(entry.id)
      if (editingId === entry.id) resetForm()
      setSaved('Entry deleted.')
      await load()
    } catch (err) {
      setError(err.message)
    }
  }

  const field = (key) => (e) => setForm({ ...form, [key]: e.target.value })

  return (
    <div>
      <div className="panel">
        <h2 className="panel-title">{editingId ? 'Edit entry' : copy.formTitle}</h2>
        <form onSubmit={submit} noValidate>
          <div className="controls">
            <label className="field">
              <span className="field-label">Amount (₹)</span>
              <input
                type="number" inputMode="decimal" step="0.01" min="0.01" placeholder="0.00" required size="8"
                value={form.amount} onChange={field('amount')}
              />
            </label>
            <label className="field">
              <span className="field-label">Category</span>
              <select required value={form.category_id} onChange={field('category_id')}>
                <option value="">Choose…</option>
                {categories.map((c) => (
                  <option key={c.id} value={c.id}>{c.name}</option>
                ))}
              </select>
            </label>
            <label className="field">
              <span className="field-label">Date</span>
              <input type="date" required value={form.date} onChange={field('date')} />
            </label>
            <label className="field input-note">
              <span className="field-label">Description</span>
              <input
                type="text" maxLength={200} placeholder={copy.placeholder}
                value={form.description} onChange={field('description')}
              />
            </label>
            <button type="submit" className="btn" disabled={busy}>
              {busy ? 'Saving…' : editingId ? 'Save changes' : 'Add entry'}
            </button>
            {editingId && (
              <button type="button" className="btn-quiet" onClick={resetForm} disabled={busy}>
                Cancel
              </button>
            )}
          </div>
        </form>
        {error && <p className="notice" role="alert">{error}</p>}
        {saved && <p className="confirm is-success" role="status">{saved}</p>}
      </div>

      <div className="panel">
        <div className="panel-head">
          <label className="field">
            <span className="field-label">Showing</span>
            <input type="month" value={month} onChange={(e) => e.target.value && setMonth(e.target.value)} />
          </label>
          {!loading && !loadError && (
            <p className="empty">
              {entries.length} {entries.length === 1 ? 'entry' : 'entries'} · {money(total)}
            </p>
          )}
        </div>

        {loadError ? (
          <p className="notice" role="alert">
            {loadError}{' '}
            <button className="btn-link" onClick={() => { setAttempt((n) => n + 1); load() }}>Try again</button>
          </p>
        ) : (
          <div className="table-scroll">
            <table className="table">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Category</th>
                  <th className="col-amount">Amount</th>
                  <th className="col-note">Description</th>
                  <th className="col-actions"><span className="sr-only">Actions</span></th>
                </tr>
              </thead>
              <tbody>
                {entries.map((e) => (
                  <tr key={e.id}>
                    <td className="cell-num cell-muted">{dayLabel(e.date)}</td>
                    <td>{e.category}</td>
                    <td className="cell-num col-amount">{money(e.amount)}</td>
                    <td className="cell-muted col-note">{e.description}</td>
                    <td className="col-actions">
                      <span className="row-actions">
                        <button className="btn-link" onClick={() => startEdit(e)}>Edit</button>
                        <button className="btn-link is-danger" onClick={() => remove(e)}>Delete</button>
                      </span>
                    </td>
                  </tr>
                ))}
                {entries.length === 0 && (
                  <tr>
                    <td colSpan="5">
                      <p className="empty">{loading ? 'Loading…' : copy.empty}</p>
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
