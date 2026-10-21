// Tests for the API client. Run with `npm test` (Node's built-in test runner;
// no extra dependencies). fetch is replaced per test, so nothing hits a server.
import { test, afterEach } from 'node:test'
import assert from 'node:assert/strict'
import {
  ApiError, UNREACHABLE, request, query, getTransactions, createTransaction, getSummary, deleteTransaction,
  login, logout, getToken, setToken, onLoggedOut,
} from './api.js'

const realFetch = globalThis.fetch
afterEach(() => {
  globalThis.fetch = realFetch
  setToken(null)
})

// A minimal Response: status plus an optional JSON body (or unparseable text).
function respond(status, body, { raw } = {}) {
  const calls = []
  globalThis.fetch = async (url, init) => {
    calls.push({ url, init })
    return {
      ok: status >= 200 && status < 300,
      status,
      json: async () => (raw !== undefined ? JSON.parse(raw) : body),
    }
  }
  return calls
}

test('query drops empty values and encodes the rest', () => {
  assert.equal(query({ month: '2026-10', type: 'expense', category_id: undefined, x: '' }),
    '?month=2026-10&type=expense')
  assert.equal(query({}), '')
})

test('GET with filters builds the URL and returns the list', async () => {
  const calls = respond(200, [{ id: 1 }])
  assert.deepEqual(await getTransactions({ month: '2026-10', type: 'income' }), [{ id: 1 }])
  assert.equal(calls[0].url, '/api/transactions?month=2026-10&type=income')
  assert.equal(calls[0].init.method, 'GET')
  assert.equal(calls[0].init.body, undefined)
})

test('POST sends JSON with a content type', async () => {
  const calls = respond(201, { id: 7 })
  await createTransaction({ type: 'expense', amount: '12.50' })
  assert.equal(calls[0].init.method, 'POST')
  assert.equal(calls[0].init.headers['Content-Type'], 'application/json')
  assert.deepEqual(JSON.parse(calls[0].init.body), { type: 'expense', amount: '12.50' })
})

test('204 No Content resolves to null', async () => {
  respond(204)
  assert.equal(await deleteTransaction(3), null)
})

test('server error message is surfaced as an ApiError with its status', async () => {
  respond(409, { error: 'A budget for this category and month already exists' })
  await assert.rejects(request('/api/budgets', { method: 'POST', body: {} }), (err) => {
    assert.ok(err instanceof ApiError)
    assert.equal(err.status, 409)
    assert.equal(err.message, 'A budget for this category and month already exists')
    return true
  })
})

test('validation error (422) keeps the field message', async () => {
  respond(422, { error: 'amount: Input should be greater than 0', details: [] })
  await assert.rejects(createTransaction({}), { message: 'amount: Input should be greater than 0' })
})

test('network failure becomes a readable "cannot reach" error', async () => {
  globalThis.fetch = async () => { throw new TypeError('Failed to fetch') }
  await assert.rejects(getTransactions(), { name: 'ApiError', message: UNREACHABLE, status: 0 })
})

test('a proxy 502/504 (backend down behind Vite) is reported as unreachable', async () => {
  respond(502, undefined, { raw: '<html>Bad gateway</html>' })
  await assert.rejects(getTransactions(), { message: UNREACHABLE })
})

test('an error without a JSON body falls back to the status code', async () => {
  respond(500, undefined, { raw: 'Internal Server Error' })
  await assert.rejects(getTransactions(), { message: 'Request failed (500)' })
})

test('a 200 with an unreadable body is an error, not undefined data', async () => {
  respond(200, undefined, { raw: '<!doctype html>' })
  await assert.rejects(request('/api/health'), { message: 'The API sent a response that could not be read' })
})

test('a list endpoint returning a non-list is rejected', async () => {
  respond(200, { unexpected: true })
  await assert.rejects(getTransactions(), { message: 'The API sent an unexpected response' })
})

test('a summary missing required fields is rejected before the page renders it', async () => {
  respond(200, { income: 1 })
  await assert.rejects(getSummary('2026-10'), { message: 'The API sent an unexpected response' })
})

// --- session handling ----------------------------------------------------------

test('login stores the token and later requests send it as a Bearer header', async () => {
  respond(200, { token: 'tok-123', user: { id: 1, name: 'Asha', email: 'asha@example.com' } })
  const user = await login({ email: 'asha@example.com', password: 'x' })
  assert.equal(user.name, 'Asha')
  assert.equal(getToken(), 'tok-123')
  const calls = respond(200, [])
  await getTransactions()
  assert.equal(calls[0].init.headers.Authorization, 'Bearer tok-123')
})

test('no token means no Authorization header', async () => {
  const calls = respond(200, [])
  await getTransactions()
  assert.equal(calls[0].init.headers.Authorization, undefined)
})

test('a 401 on a signed-in request forgets the token and tells listeners once', async () => {
  setToken('expired-token')
  let told = 0
  const stop = onLoggedOut(() => { told += 1 })
  respond(401, { error: 'Please log in to continue' })
  await assert.rejects(getTransactions(), { status: 401, message: 'Please log in to continue' })
  assert.equal(getToken(), null)
  assert.equal(told, 1)
  stop()
})

test('a wrong password shows the server message and does not fire a sign-out', async () => {
  let told = 0
  const stop = onLoggedOut(() => { told += 1 })
  respond(401, { error: 'Email or password is incorrect' })
  await assert.rejects(login({ email: 'a@b.co', password: 'nope' }), { message: 'Email or password is incorrect' })
  assert.equal(told, 0)
  stop()
})

test('logout clears the token even when the server cannot be reached', async () => {
  setToken('tok-456')
  globalThis.fetch = async () => { throw new TypeError('Failed to fetch') }
  await logout()
  assert.equal(getToken(), null)
})

test('a login response without a token is rejected, and nothing is stored', async () => {
  respond(200, { user: { id: 1 } })
  await assert.rejects(login({ email: 'a@b.co', password: 'x' }), { message: 'The API sent an unexpected response' })
  assert.equal(getToken(), null)
})
