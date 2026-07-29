import { useCallback, useEffect, useState } from 'react'
import { getCategories, createCategory, deleteCategory, getExpenses } from '../api'

export default function Categories() {
  const [categories, setCategories] = useState([])
  const [counts, setCounts] = useState({})
  const [name, setName] = useState('')
  const [error, setError] = useState('')

  // Entry counts come along so a category in use can say so up front, rather
  // than letting the delete fail and explain afterwards.
  const load = useCallback(() => {
    getCategories().then(setCategories).catch((err) => setError(err.message))
    getExpenses()
      .then((expenses) => {
        const tally = {}
        for (const e of expenses) tally[e.category_id] = (tally[e.category_id] || 0) + 1
        setCounts(tally)
      })
      .catch((err) => setError(err.message))
  }, [])

  useEffect(() => { load() }, [load])

  const submit = async (e) => {
    e.preventDefault()
    setError('')
    try {
      await createCategory(name)
      setName('')
      load()
    } catch (err) {
      setError(err.message)
    }
  }

  const remove = async (id) => {
    if (!confirm('Delete this category?')) return
    setError('')
    try {
      await deleteCategory(id)
      load()
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <div>
      <div className="panel">
        <h2 className="panel-title">New category</h2>
        <form onSubmit={submit} className="controls">
          <label className="field input-note">
            <span className="field-label">Name</span>
            <input
              type="text" placeholder="Groceries, Rent, Travel…" required
              value={name} onChange={(e) => setName(e.target.value)}
            />
          </label>
          <button type="submit" className="btn">Add category</button>
        </form>
        {error && <p className="notice">{error}</p>}
      </div>

      <div className="panel">
        <h2 className="panel-title">In use</h2>
        <div className="table-scroll">
        <table className="table">
          <thead>
            <tr>
              <th>Category</th>
              <th className="col-amount">Entries</th>
              <th className="col-actions"><span className="sr-only">Actions</span></th>
            </tr>
          </thead>
          <tbody>
            {categories.map((c) => {
              const used = counts[c.id] || 0
              return (
                <tr key={c.id}>
                  <td>{c.name}</td>
                  <td className="cell-num col-amount cell-muted">{used}</td>
                  <td className="col-actions">
                    {used > 0 ? (
                      <span className="empty">in use</span>
                    ) : (
                      <button className="btn-link is-danger" onClick={() => remove(c.id)}>Delete</button>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
        </div>
        <p className="confirm">A category can only be deleted once nothing is filed under it.</p>
      </div>
    </div>
  )
}
