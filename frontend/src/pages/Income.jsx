import { useCallback, useEffect, useState } from 'react'
import { getIncome, createIncome, updateIncome, deleteIncome } from '../api'
import { today, currentMonth, dayLabel, money } from '../format'

// A function, not a const: a module-level date goes stale once the app is left
// open past midnight.
const emptyForm = () => ({ amount: '', source: '', date: today(), note: '' })

export default function Income() {
  const [month, setMonth] = useState(currentMonth)
  const [entries, setEntries] = useState([])
  const [form, setForm] = useState(emptyForm)
  const [busy, setBusy] = useState(false)
  const [editingId, setEditingId] = useState(null)
  const [error, setError] = useState('')

  const load = useCallback(() => {
    getIncome(month).then(setEntries).catch((err) => setError(err.message))
  }, [month])

  useEffect(() => { load() }, [load])

  const total = entries.reduce((sum, e) => sum + e.amount, 0)

  const submit = async (e) => {
    e.preventDefault()
    setError('')
    const payload = {
      amount: parseFloat(form.amount),
      source: form.source,
      date: form.date,
      note: form.note,
    }
    setBusy(true)
    try {
      if (editingId) {
        await updateIncome(editingId, payload)
      } else {
        await createIncome(payload)
      }
      setForm(emptyForm())
      setEditingId(null)
      // Follow the entry to its own month, otherwise saving one outside the
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

  const startEdit = (entry) => {
    setEditingId(entry.id)
    setForm({
      amount: String(entry.amount),
      source: entry.source,
      date: entry.date,
      note: entry.note || '',
    })
  }

  const remove = async (id) => {
    if (!confirm('Delete this income entry? This cannot be undone.')) return
    setError('')
    try {
      await deleteIncome(id)
      load()
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <div>
      <div className="panel">
        <h2 className="panel-title">{editingId ? 'Edit entry' : 'What came in'}</h2>
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
              <span className="field-label">Source</span>
              <input
                type="text" placeholder="Salary, Freelance…" required size="14"
                value={form.source} onChange={(e) => setForm({ ...form, source: e.target.value })}
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
                type="text" placeholder="Anything worth remembering"
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
        <div className="panel-head">
          <label className="field">
            <span className="field-label">Showing</span>
            <input type="month" value={month} onChange={(e) => setMonth(e.target.value)} />
          </label>
          <p className="empty">
            {entries.length} {entries.length === 1 ? 'entry' : 'entries'} · {money(total)}
          </p>
        </div>

        <div className="table-scroll">
          <table className="table">
            <thead>
              <tr>
                <th>Date</th>
                <th>Source</th>
                <th className="col-amount">Amount</th>
                <th className="col-note">Note</th>
                <th className="col-actions"><span className="sr-only">Actions</span></th>
              </tr>
            </thead>
            <tbody>
              {entries.map((e) => (
                <tr key={e.id}>
                  <td className="cell-num cell-muted">{dayLabel(e.date)}</td>
                  <td>{e.source}</td>
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
              {entries.length === 0 && (
                <tr>
                  <td colSpan="5">
                    <p className="empty">
                      Nothing recorded for this month. Add what came in and Savings can
                      show what share of it you kept.
                    </p>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
