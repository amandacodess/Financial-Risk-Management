# LodgeLedger API — FastAPI + Supabase PostgreSQL

The backend for the LodgeLedger dashboard (Financial Risk and Budget Monitoring).
It replaces the original Go/SQLite backend, which has been removed. It remains in
git history at commit `8ed0f0d`.

```
backend/
  main.py            app, CORS, read-only guard, error handlers, /api/health
  auth.py            password hashing (scrypt), session tokens, current-user dependency
  config.py          settings from environment variables; today's date in APP_TZ
  database.py        PostgresRepository: all SQL, psycopg 3 connection pool
  schemas.py         Pydantic request/response models and validation rules
  routes/            auth, categories, transactions, budgets, dashboard
                     (+ risks, analytics), savings (goals, settings)
  services/
    analytics.py     pure calculations: totals, savings rate, utilization,
                     pace, forecast, goal progress
    risk_engine.py   the risk rules
  tests/             unit tests (in-memory fake) + integration tests (real SQL)
sql/schema.sql       tables, constraints, indexes, RLS (v2: user accounts)
sql/reset_v1.sql     DESTRUCTIVE: drops the old single-user tables before upgrading
```

The `/api/risks` route lives in `routes/dashboard.py` with the summary, because both
are built from the same monthly report.

## Database access: one approach

The API talks to Supabase **directly as PostgreSQL** with psycopg 3 and a small
connection pool. It doesn't use the `supabase-py` REST client or an ORM. The reasons:

- The dashboard is mostly `GROUP BY` aggregates. That's one SQL statement here,
  but awkward through Supabase's REST layer.
- The constraint errors (duplicate budget, wrong category type, category in use)
  come back as specific Postgres error classes, which the repository maps to 409/422.
- No Supabase service-role key is needed anywhere. The only secret is
  `DATABASE_URL`, and it stays server-side.

All SQL lives in `database.py`. Routes get the repository through a FastAPI
dependency, so the unit tests replace it with an in-memory fake.

## Definitions (read before the numbers)

| Term | Meaning |
|---|---|
| **Net cash flow** | Income minus expenses *recorded for the selected month*. It is **not a bank balance**: it knows nothing about money held before the month or anything not entered in LodgeLedger. The API never reports a "balance". |
| **Savings rate** | Net cash flow ÷ income × 100. `null` when the month has no income; dividing by zero has no meaningful rate. Can be negative. |
| **Utilization** | Category spending ÷ that category's budget for the month × 100. `null` when there is no budget. |
| **Total budget utilization** | *All* expenses ÷ sum of category budgets. Spending in categories without a budget counts, so this can exceed 100% while every budgeted category is within its limit. Lines with `status: "no_budget"` show where. |
| **Projected expenses** | Straight-line pace: spent so far × days in month ÷ days elapsed. Equals actual spending for a past month. |
| **Forecast** | Per-category average over the 3 months before the selected month, counting only months with any spending. |

Money is `numeric(12,2)` in Postgres and `Decimal` in Python, so it is never a
float on the server. Responses carry amounts as JSON numbers, because the
frontend does arithmetic on them; a 2-decimal value round-trips exactly.

Dates are plain `YYYY-MM-DD` calendar dates with no time. A **month** is
`YYYY-MM` in the API, stored as its first day, and covers the half-open range
[1st, 1st of next month). "Current month" is decided in `APP_TZ`
(default `Asia/Kolkata`), not the server's clock zone.

## Risk rules

These are illustrative dashboard rules, not financial advice or a standard.
They're in `services/risk_engine.py`; the thresholds come from environment variables.

| Code | Severity | Fires when |
|---|---|---|
| `budget_warning` | warning | a category has used ≥ `BUDGET_WARNING_PCT` (80) % of its budget and is not over it. **Exactly 100% is a warning** ("at limit"). |
| `budget_exceeded` | critical | a category's spending is **above** `BUDGET_EXCEEDED_PCT` (100) % of its budget |
| `negative_cash_flow` | critical | expenses > income for the month, including any spending in a month with no income |
| `projected_overspend` | warning | current month only: total spending is still within the total budget, but the pace projects past it |

Statuses use the exact ratio. 79.99% is `ok` even though it displays as `80.0`.
Empty months, zero income and zero budgets produce no risks and no errors.

## Supabase setup

1. Create a project at <https://supabase.com/dashboard>. Note the database password you choose.
2. **SQL Editor → New query**, paste the contents of `sql/schema.sql`, and click **Run**.
   The script is re-runnable: it only creates things that are missing and never drops data.
   - **Upgrading from the earlier single-user schema?** Run `sql/reset_v1.sql` first.
     It deletes the old tables and everything in them, and refuses to run if a `users`
     table already exists.
3. Click **Connect** at the top of the project, choose **Session pooler**, and copy the URI.
   The direct connection is IPv6-only, which many hosts and home networks cannot reach.
4. Configure the backend:
   ```bash
   cd backend
   cp .env.example .env      # then paste the connection string into DATABASE_URL
   ```
   `.env` is gitignored. **Never** put `DATABASE_URL` or any Supabase secret in
   `frontend/` or in a `VITE_*` variable; Vite publishes those to every browser.

### Row Level Security

RLS is **enabled on every table, with no policies**. This is what that means:

- Supabase automatically exposes `public` tables through its REST/GraphQL API,
  which anyone holding the project's public *anon* key can call. With RLS on and
  no policies, that API returns no rows and refuses all writes. That is intended,
  and it matters more now that `users` holds password hashes: LodgeLedger's browser
  code never talks to Supabase directly.
- The FastAPI backend connects as the `postgres` role, which owns the tables and
  therefore **bypasses RLS**. Per-user access is enforced by the API (every query
  filters on the signed-in user's id) and by the schema's composite foreign keys,
  which stop one account's rows pointing at another account's categories or goals.
- So the database is only as protected as `DATABASE_URL` (keep it secret) and the
  API (see the next section). FastAPI doesn't make it secure on its own.

### Accounts and security boundary

- **Registration** (`POST /api/auth/register`) takes a name, email and password of
  at least 8 characters. It creates the account with its own copy of the default
  categories and signs in straight away.
- **Passwords** are hashed with scrypt (Python's `hashlib`), using a random salt
  each time. The password itself is never stored or logged.
- **Sessions:** signing in returns a random 256-bit token. The browser keeps it in
  `localStorage` and sends it as `Authorization: Bearer <token>`. The database
  stores only its SHA-256, so a copy of the `sessions` table can't be used to sign
  in. Sessions expire after `SESSION_DAYS` (default 7), and signing out deletes one.
- **Isolation:** every data endpoint needs a valid session (otherwise 401). A record
  that belongs to another account behaves exactly like one that doesn't exist (404).
- A wrong email and a wrong password get the same 401 message and take the same time,
  so the login form doesn't reveal which emails have accounts.
- CORS only admits the origins in `CORS_ORIGINS`. CORS is a browser rule, not
  access control: it doesn't stop `curl`. That's what the login check is for.
- Errors never include SQL, stack traces or connection details. Those go to the
  server log, and the connection string is never logged.
- `ALLOW_WRITES=false` freezes a deployment: every write, sign-ups included, returns 403.

**Known limits (out of scope for the deadline):**
- No email verification, so an account isn't proof that someone owns that address.
- No password reset.
- No rate limiting on sign-in attempts.
- A token kept in `localStorage` could be read by any script running on the page. React
  escapes everything it renders, and the app loads no third-party scripts, which keeps
  that risk low. httpOnly cookies would be the next step, but they need the frontend
  and API on the same site.

## Run locally

```bash
cd backend
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt      # macOS/Linux: .venv/bin/pip
.venv/Scripts/uvicorn main:app --port 8080 --env-file .env --reload
```

Port 8080 is what the Vite dev server proxies `/api` to. Then open:

- Swagger UI: <http://localhost:8080/docs>. Each endpoint has **Try it out**.
- Health check: `curl http://localhost:8080/api/health` → `{"status":"ok","database":"ok"}`.
  You get a 503 with `"database":"unavailable"` if the database can't be reached.

## Tests

```bash
cd backend
.venv/Scripts/python -m pytest              # unit tests; integration tests skip
```

| Kind | Files | Needs |
|---|---|---|
| Unit: calculations | `test_analytics.py`, `test_risks.py` (first half) | nothing |
| Unit: HTTP API | `test_transactions.py`, `test_budgets.py`, `test_risks.py`, `test_app.py` | nothing; uses the in-memory `FakeRepository` and a fixed "today" |
| Integration: real SQL | `test_integration.py` (marker `integration`) | `TEST_DATABASE_URL` |

The unit tests remove `DATABASE_URL` from their environment before starting, so
they can't reach a real database even if one is configured.

To run the integration tests, point `TEST_DATABASE_URL` at a **disposable**
PostgreSQL database: a local Postgres or a separate Supabase project, never
production. Each run creates a schema named `ledger_test_<random>`, applies
`sql/schema.sql` inside it, and drops only that schema afterwards. The run
refuses to start if `TEST_DATABASE_URL` equals `DATABASE_URL`.

```bash
TEST_DATABASE_URL="postgresql://postgres:PASSWORD@127.0.0.1:5432/postgres" .venv/Scripts/python -m pytest -m integration -v
```

### Test data

All test data is fictional. The unit tests build their data in memory. For a demo,
register an account with a made-up name and email (e.g. `demo@example.com`) and
enter a few transactions through the UI. Each account starts empty apart from its
default categories. Don't load real bank statements into a demo project.

## API reference

Base path `/api`. JSON in and out. **Every error** has the form
`{"error": "message"}`, and validation errors add `"details": [{"field", "message"}]`.

| Status | When |
|---|---|
| 200 / 201 / 204 | OK / created / deleted |
| 401 | not signed in, session expired or signed out, or wrong email/password at login |
| 403 | write attempted while `ALLOW_WRITES=false` |
| 404 | record not found (or it belongs to another account) |
| 409 | duplicate (account email, budget for category+month, category name, goal name) or category still in use |
| 422 | invalid input: amount ≤ 0 or with more than 2 decimals, unknown type, malformed date or month, unknown field, missing or mismatched category |
| 503 | database unreachable or `DATABASE_URL` not set |
| 500 | unexpected error (generic message only) |

Every endpoint except `health`, `auth/register` and `auth/login` needs the header
`Authorization: Bearer <token>`.

| Method & path | Purpose |
|---|---|
| `GET /health` | API and database status (public) |
| `POST /auth/register` | `{name, email, password}` → 201 `{token, user}` |
| `POST /auth/login` | `{email, password}` → `{token, user}`, or 401 |
| `POST /auth/logout` | ends the current session |
| `GET /auth/me` | the signed-in user `{id, name, email}` |
| `GET /categories?type=` | categories with `transaction_count` |
| `POST /categories` | `{name, type}` |
| `DELETE /categories/{id}` | 409 if any transaction uses it; its budgets are removed with it |
| `GET /transactions?month=&type=&category_id=` | newest first; all filters optional |
| `POST /transactions` | create |
| `PUT /transactions/{id}` | full replacement |
| `DELETE /transactions/{id}` | delete |
| `GET /budgets?month=` | list |
| `POST /budgets` | `{category_id, month, amount}`; one per expense category per month |
| `PUT /budgets/{id}` | `{amount}` |
| `DELETE /budgets/{id}` | delete |
| `GET /dashboard/summary?month=` | totals, budget vs actual, pace, forecast, risks |
| `GET /risks?month=` | just the risks |
| `GET /analytics/monthly?months=6&end=` | per-month series, oldest first (1–24 months) |
| `GET /goals` | savings goals with progress and pace |
| `POST /goals` | `{name, target_amount, target_date?}` |
| `DELETE /goals/{id}` | deletes the goal and its contributions |
| `POST /goals/{id}/contributions` | `{amount, date, description?}` |
| `GET /settings`, `PUT /settings` | `{savings_target}` |

`month` defaults to the current month wherever it's optional on the dashboard routes.

### Examples

Sign in first, then send the token with every request (fictional account):

```bash
curl -X POST http://localhost:8080/api/auth/register -H "Content-Type: application/json" \
  -d '{"name":"Demo User","email":"demo@example.com","password":"demo-pass-123"}'
# → 201 {"token":"<TOKEN>","user":{"id":1,"name":"Demo User","email":"demo@example.com"}}
TOKEN=<TOKEN>   # or POST /api/auth/login with the same email and password
```

```bash
curl -X POST http://localhost:8080/api/transactions \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"type":"expense","amount":"249.50","category_id":1,"date":"2026-10-05","description":"Lunch"}'
```
```json
{"id":42,"type":"expense","amount":249.5,"category_id":1,"category":"Food","date":"2026-10-05","description":"Lunch"}
```

Each category has a `type`. Income is filed under an income category (Salary,
Freelance, …), and the database rejects an expense under an income category:

```json
{"error":"category_id does not exist or is not an expense category"}
```

```bash
curl -X POST http://localhost:8080/api/budgets -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"category_id":1,"month":"2026-10","amount":"10000"}'
# second time → 409 {"error":"A budget for this category and month already exists"}
```

`GET /api/dashboard/summary?month=2026-10` (abridged, for an account with fictional entries):

```json
{
  "month": "2026-10",
  "income": 58000.0, "expenses": 39000.25, "net_cash_flow": 18999.75, "savings_rate_pct": 32.8,
  "budget_total": 35500.0, "budget_utilization_pct": 109.9,
  "categories": [
    {"category_id": 3, "category": "Shopping", "budget": 5000.0, "spent": 9800.0,
     "remaining": -4800.0, "utilization_pct": 196.0, "status": "exceeded"},
    {"category_id": 5, "category": "Entertainment", "budget": null, "spent": 799.0,
     "remaining": null, "utilization_pct": null, "status": "no_budget"}
  ],
  "pace": {"days_elapsed": 20, "days_in_month": 31, "projected_expenses": 60450.39},
  "forecast": [{"category_id": 4, "category": "Bills", "predicted": 16850.75}],
  "risks": [
    {"code": "budget_exceeded", "severity": "critical", "category_id": 3, "category": "Shopping",
     "value": 196.0, "threshold": 5000.0,
     "message": "Shopping is over budget: ₹9,800.00 spent of ₹5,000.00 (196.0%)."}
  ]
}
```

`GET /api/analytics/monthly?months=2&end=2026-10`:

```json
{"months": [
  {"month": "2026-09", "income": 52000.0, "expenses": 27500.25, "net_cash_flow": 24499.75, "savings_rate_pct": 47.1},
  {"month": "2026-10", "income": 58000.0, "expenses": 39000.25, "net_cash_flow": 18999.75, "savings_rate_pct": 32.8}
 ], "average_savings_rate_pct": 40.0}
```

Validation error:

```json
{"error": "amount: Input should be greater than 0",
 "details": [{"field": "amount", "message": "Input should be greater than 0"}]}
```
