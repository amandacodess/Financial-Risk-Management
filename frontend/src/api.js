async function request(path, options) {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.error || `Request failed: ${res.status}`)
  }
  if (res.status === 204) return null
  return res.json()
}

export const getCategories = () => request('/api/categories')
export const createCategory = (name) =>
  request('/api/categories', { method: 'POST', body: JSON.stringify({ name }) })
export const deleteCategory = (id) =>
  request(`/api/categories/${id}`, { method: 'DELETE' })

export const getExpenses = (month) =>
  request(month ? `/api/expenses?month=${month}` : '/api/expenses')
export const createExpense = (expense) =>
  request('/api/expenses', { method: 'POST', body: JSON.stringify(expense) })
export const updateExpense = (id, expense) =>
  request(`/api/expenses/${id}`, { method: 'PUT', body: JSON.stringify(expense) })
export const deleteExpense = (id) =>
  request(`/api/expenses/${id}`, { method: 'DELETE' })

export const getIncome = (month) =>
  request(month ? `/api/income?month=${month}` : '/api/income')
export const createIncome = (entry) =>
  request('/api/income', { method: 'POST', body: JSON.stringify(entry) })
export const updateIncome = (id, entry) =>
  request(`/api/income/${id}`, { method: 'PUT', body: JSON.stringify(entry) })
export const deleteIncome = (id) =>
  request(`/api/income/${id}`, { method: 'DELETE' })

export const getSavings = () => request('/api/savings')
export const createGoal = (goal) =>
  request('/api/goals', { method: 'POST', body: JSON.stringify(goal) })
export const updateGoal = (id, goal) =>
  request(`/api/goals/${id}`, { method: 'PUT', body: JSON.stringify(goal) })
export const deleteGoal = (id) => request(`/api/goals/${id}`, { method: 'DELETE' })
export const getContributions = (goalId) => request(`/api/goals/${goalId}/contributions`)
export const addContribution = (goalId, contribution) =>
  request(`/api/goals/${goalId}/contributions`, {
    method: 'POST',
    body: JSON.stringify(contribution),
  })
export const deleteContribution = (id) =>
  request(`/api/contributions/${id}`, { method: 'DELETE' })

export const getSettings = () => request('/api/settings')
// Sends only what changed: the server leaves omitted fields as they are.
export const updateSettings = (patch) =>
  request('/api/settings', { method: 'PUT', body: JSON.stringify(patch) })

export const getPrediction = () => request('/api/prediction')
export const getInsight = (refresh) =>
  request(refresh ? '/api/insight?refresh=1' : '/api/insight')
