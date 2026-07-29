# Ledger

A private expense tracker with a Go/SQLite backend and a React frontend. It
records what you spend, what comes in, and what you put aside, forecasts next
month from your own history, and warns you when this month's pace overshoots
your budget.

Everything is local. The one exception is the written analysis, which is opt-in
and described below.

## What it does

**Overview** — what you have spent against your budget, where it went, what you
kept, next month's forecast per category, and a written analysis if you have
turned that on.

**Expenses / Income** — add, edit and delete entries, filtered by month.

**Savings** — a monthly savings rate (what came in, what went out, what share you
kept) with six months of history, plus named goals. A goal with a deadline is
judged on pace: what it needs per month against what it is actually getting.
A goal without one just tracks the total.

**Categories / Budget** — the things you set up once: your categories, your
monthly spending budget, and your monthly savings target.

## Running locally

Two servers, side by side.

**Backend** (Go, listens on `:8080` by default, creates `backend/expense-tracker.db`):

    cd backend
    go run .

If `8080` is already taken, set `PORT` to a free port before starting the server.

**Frontend** (Vite + React, listens on `:5173`, proxies `/api` to the backend port):

    cd frontend
    npm install   # first time only
    npm run dev

If you changed the backend port, set `VITE_BACKEND_PORT` to the same value
before running the frontend dev server.

Open the URL Vite prints (typically http://localhost:5173).

## The written analysis (optional)

Overview can carry a short written review of your figures, produced by Google's
Gemini. It is off unless you provide a key.

    cd backend
    cp .env.example .env
    # paste your key from https://aistudio.google.com/apikey
    go run .

The server prints `gemini: enabled` on startup when it finds a key. `.env` is
gitignored.

Without a key nothing breaks: budgets, savings, goals and the per-category
forecast are all computed locally from your own data and never need the network.
The analysis panel simply explains that it is not configured.

**What gets sent, if you turn it on:** monthly totals per category, monthly
income totals, your budget and savings target, and your goal names and progress.
**The notes you write on individual entries are never sent.** An answer is reused
until your figures change, so reloading the page does not spend another call.

`GEMINI_MODEL` overrides the model (default `gemini-3.6-flash`). Use a 3-series
model — the request sets a thinking level, which older models reject.

## Tests

    cd backend
    go test ./...

    cd frontend
    npm run lint
