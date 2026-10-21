# LodgeLedger — Financial Risk and Budget Monitoring Dashboard

A personal finance dashboard: record income and expenses, set monthly budgets per
category, and see budget-versus-actual, savings rate and rule-based risk alerts.
Each person signs in to their own account, and accounts can't see each other's data.

**Stack:** React + Vite frontend (`frontend/`), FastAPI backend (`backend/`),
Supabase PostgreSQL database (`sql/`).

> Based on [mohak9146-dotcom/Finance-Tracker](https://github.com/mohak9146-dotcom/Finance-Tracker)
> (commit `8ed0f0d`), reused with the author's permission. The original
> repository has no licence file. Its React interface (design, navigation and
> pages) is kept. Its Go/SQLite backend and the optional Gemini written analysis
> were removed and replaced by the FastAPI + PostgreSQL backend. The original
> Go code and its tests stay in git history at that commit. Their test cases
> were ported to pytest (`backend/tests/`).

## What it does

**Sign in / Create account** — email and password. Each new account starts empty,
with its own default categories. The light/dark mode switch is on every screen.

**Overview** — pick a month and see income, expenses, net cash flow and savings
rate; spending pace against your total budget; budget vs actual per category;
risk alerts; where the money went; and a forecast from the three months before.

**Expenses / Income** — add, edit and delete entries, filtered by month. Each
entry belongs to an expense or income category.

**Savings** — six months of savings history, plus named goals judged on pace.

**Categories / Budget** — your categories, monthly budgets per expense category,
and your monthly savings target.

## Running locally

Backend setup (Supabase, `.env`, accounts, API reference, risk rules, tests): see
[backend/README.md](backend/README.md). In short: run `sql/schema.sql` in the
Supabase SQL Editor, put the Session pooler connection string in `backend/.env`,
then start both servers.

    cd backend
    .venv/Scripts/uvicorn main:app --port 8080 --env-file .env

    cd frontend
    npm install   # first time only
    npm run dev

Open http://localhost:5173. Vite proxies `/api` to port 8080. If you use a
different port, set `VITE_BACKEND_PORT` to match.

## Tests

    cd backend
    .venv/Scripts/python -m pytest

    cd frontend
    npm test
    npm run lint
    npm run build
