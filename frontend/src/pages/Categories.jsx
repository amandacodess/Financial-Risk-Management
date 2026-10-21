import { useCallback, useEffect, useState } from 'react'
import { getCategories, createCategory, deleteCategory } from '../api'

const TYPE_LABEL = { expense: 'Expense', income: 'Income' }

export default function Categories() {
  const [categories, setCategories] = useState([])
  const [loading, setLoading] = useState(true)
  const [form, setForm] = useState({ name: '', type: 'expense' })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [saved, setSaved] = useState('')

  // Each category arrives with its entry count, so one in use can say so up
  // front rather than letting the delete fail and explain afterwards.
  const load = useCallback(() => {
    setLoading(true)
    return getCategories()
      .then(setCategories)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => { load() }, [load])

  const submit = async (e) => {
    e.preventDefault()
    setError('')
    setSaved('')
    const name = form.name.trim()
    if (!name) {
      setError('Enter a category name.')
      return
    }
    setBusy(true)
    try {
      await createCategory({ name, type: form.type })
      setForm({ ...form, name: '' })
      setSaved(`Added “${name}”.`)
      await load()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const remove = async (category) => {
    if (!confirm(`Delete “${category.name}”? Any budgets set for it go too.`)) return
    setError('')
    setSaved('')
    try {
      await deleteCategory(category.id)
      setSaved(`Deleted “${category.name}”.`)
      await load()
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <div>
      <div className="panel">
        <h2 className="panel-title">New category</h2>
        <form onSubmit={submit} className="controls" noValidate>
          <label className="field input-note">
            <span className="field-label">Name</span>
            <input
              type="text" placeholder="Groceries, Rent, Travel…" required maxLength={50}
              value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })}
            />
          </label>
          <label className="field">
            <span className="field-label">For</span>
            <select value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value })}>
              <option value="expense">Expenses</option>
              <option value="income">Income</option>
            </select>
          </label>
          <button type="submit" className="btn" disabled={busy}>{busy ? 'Adding…' : 'Add category'}</button>
        </form>
        {error && <p className="notice" role="alert">{error}</p>}
        {saved && <p className="confirm is-success" role="status">{saved}</p>}
      </div>

      <div className="panel">
        <h2 className="panel-title">In use</h2>
        <div className="table-scroll">
          <table className="table">
            <thead>
              <tr>
                <th>Category</th>
                <th>For</th>
                <th className="col-amount">Entries</th>
                <th className="col-actions"><span className="sr-only">Actions</span></th>
              </tr>
            </thead>
            <tbody>
              {categories.map((c) => (
                <tr key={c.id}>
                  <td>{c.name}</td>
                  <td className="cell-muted">{TYPE_LABEL[c.type]}</td>
                  <td className="cell-num col-amount cell-muted">{c.transaction_count}</td>
                  <td className="col-actions">
                    {c.transaction_count > 0 ? (
                      <span className="empty">in use</span>
                    ) : (
                      <button className="btn-link is-danger" onClick={() => remove(c)}>Delete</button>
                    )}
                  </td>
                </tr>
              ))}
              {categories.length === 0 && (
                <tr>
                  <td colSpan="4">
                    <p className="empty">{loading ? 'Loading…' : 'No categories yet.'}</p>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        <p className="confirm">A category can only be deleted once nothing is filed under it.</p>
      </div>
    </div>
  )
}
