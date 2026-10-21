// The one place the interface talks to the LodgeLedger API (FastAPI). Every page
// goes through here, so errors look the same everywhere: an ApiError whose
// message can be shown to the reader as it is.

// Empty in development: Vite proxies /api to the backend (see vite.config.js).
// In production, the API's origin, e.g. https://ledger-api.example.com.
// Only ever a public URL — never a database password or Supabase key.
const BASE = (import.meta.env?.VITE_API_BASE_URL ?? '').replace(/\/+$/, '')

export class ApiError extends Error {
  constructor(message, status = 0) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

export const UNREACHABLE = 'Cannot reach the LodgeLedger API. Check that the backend is running.'

// --- session ---------------------------------------------------------------
// The login token from /api/auth/login or /register. Kept in localStorage so a
// reload stays signed in; sent as "Authorization: Bearer <token>". It is a
// random session id the server can revoke (logout, expiry), never a password.
const TOKEN_KEY = 'lodgeledger-token'
let token = null
try {
  token = localStorage.getItem(TOKEN_KEY)
} catch {
  // No storage (private mode, tests): the session just lasts until reload.
}

export const getToken = () => token

export function setToken(next) {
  token = next
  try {
    if (next) localStorage.setItem(TOKEN_KEY, next)
    else localStorage.removeItem(TOKEN_KEY)
  } catch {
    // Same as above: memory only.
  }
}

// Told when the server stops accepting our token (expired or revoked), so the
// app can return to the sign-in screen from whichever page noticed.
const loggedOutListeners = new Set()
export function onLoggedOut(listener) {
  loggedOutListeners.add(listener)
  return () => loggedOutListeners.delete(listener)
}

export async function request(path, { method = 'GET', body } = {}) {
  const headers = {}
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  if (token) headers.Authorization = `Bearer ${token}`
  let res
  try {
    res = await fetch(BASE + path, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    })
  } catch {
    // fetch only rejects when no response arrived at all (server down, CORS, offline).
    throw new ApiError(UNREACHABLE, 0)
  }
  if (res.status === 204) return null

  const data = await res.json().catch(() => undefined)
  if (res.status === 401 && token) {
    // Our session is no longer valid: forget it everywhere, once.
    setToken(null)
    loggedOutListeners.forEach((listener) => listener())
  }
  if (!res.ok) {
    // The API always answers {"error": "..."}; anything else is a proxy or host page.
    const message = typeof data?.error === 'string' ? data.error : `Request failed (${res.status})`
    throw new ApiError(res.status === 502 || res.status === 504 ? UNREACHABLE : message, res.status)
  }
  if (data === undefined) throw new ApiError('The API sent a response that could not be read', res.status)
  return data
}

// Guards for the shapes pages rely on: a malformed response becomes a readable
// error instead of a crash deep inside a chart.
const list = (data) => {
  if (!Array.isArray(data)) throw new ApiError('The API sent an unexpected response')
  return data
}
const object = (data, ...keys) => {
  if (!data || typeof data !== 'object' || keys.some((k) => !(k in data))) {
    throw new ApiError('The API sent an unexpected response')
  }
  return data
}

export const query = (params = {}) => {
  const entries = Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== '')
  return entries.length ? `?${new URLSearchParams(entries)}` : ''
}

export const getHealth = () => request('/api/health')

// Register and login both answer {token, user}: keep the token, return the user.
const startSession = (data) => {
  object(data, 'token', 'user')
  setToken(data.token)
  return data.user
}
export const register = (account) =>
  request('/api/auth/register', { method: 'POST', body: account }).then(startSession)
export const login = (credentials) =>
  request('/api/auth/login', { method: 'POST', body: credentials }).then(startSession)
export const getMe = () => request('/api/auth/me').then((d) => object(d, 'id', 'name', 'email'))
// The local token goes regardless: if the server cannot be told (offline), the
// session still ends on this device and expires server-side on its own.
export const logout = () =>
  request('/api/auth/logout', { method: 'POST' }).catch(() => null).finally(() => setToken(null))

export const getCategories = (type) => request(`/api/categories${query({ type })}`).then(list)
export const createCategory = (category) => request('/api/categories', { method: 'POST', body: category })
export const deleteCategory = (id) => request(`/api/categories/${id}`, { method: 'DELETE' })

// filters: { month: 'YYYY-MM', type: 'income' | 'expense', category_id }
export const getTransactions = (filters) => request(`/api/transactions${query(filters)}`).then(list)
export const createTransaction = (tx) => request('/api/transactions', { method: 'POST', body: tx })
export const updateTransaction = (id, tx) => request(`/api/transactions/${id}`, { method: 'PUT', body: tx })
export const deleteTransaction = (id) => request(`/api/transactions/${id}`, { method: 'DELETE' })

export const getBudgets = (month) => request(`/api/budgets${query({ month })}`).then(list)
export const createBudget = (budget) => request('/api/budgets', { method: 'POST', body: budget })
export const updateBudget = (id, amount) => request(`/api/budgets/${id}`, { method: 'PUT', body: { amount } })
export const deleteBudget = (id) => request(`/api/budgets/${id}`, { method: 'DELETE' })

export const getSummary = (month) =>
  request(`/api/dashboard/summary${query({ month })}`).then((d) =>
    object(d, 'income', 'expenses', 'net_cash_flow', 'categories', 'pace', 'forecast', 'risks'))
export const getMonthly = (months = 6, end) =>
  request(`/api/analytics/monthly${query({ months, end })}`).then((d) => object(d, 'months'))

export const getGoals = () => request('/api/goals').then(list)
export const createGoal = (goal) => request('/api/goals', { method: 'POST', body: goal })
export const deleteGoal = (id) => request(`/api/goals/${id}`, { method: 'DELETE' })
export const addContribution = (goalId, contribution) =>
  request(`/api/goals/${goalId}/contributions`, { method: 'POST', body: contribution })

export const getSettings = () => request('/api/settings').then((d) => object(d, 'savings_target'))
export const updateSettings = (patch) => request('/api/settings', { method: 'PUT', body: patch })
