-- LodgeLedger schema for Supabase PostgreSQL (v2: user accounts).
--
-- Safe to run on a new project and safe to re-run: every statement is
-- IF NOT EXISTS / ON CONFLICT DO NOTHING. Nothing here drops or rewrites data.
-- Apply it in the Supabase dashboard (SQL Editor → paste → Run) or with
--   psql "$DATABASE_URL" -f sql/schema.sql
--
-- Upgrading a project that has the v1 tables (no users)? Run
-- sql/reset_v1.sql first — it is destructive and says so.
--
-- Conventions
--   * Every row belongs to exactly one user (user_id). Composite foreign keys
--     make the database itself refuse to link one user's transaction to another
--     user's category or goal — not just the API.
--   * Money is numeric(12,2): exact, never floating point. Amounts are always
--     positive; transactions.type says which direction the money moved.
--   * A transaction's date is a plain calendar date (no time, no timezone).
--   * A month is stored as the date of its first day (2026-10-01) and is the
--     half-open range [first day, first day of next month).
--   * Unqualified table names, so the same file can build an isolated schema
--     for integration tests via search_path.

create table if not exists users (
  id            bigint generated always as identity primary key,
  email         text not null check (length(email) <= 254 and email ~ '^[^@\s]+@[^@\s]+\.[^@\s]+$'),
  name          text not null check (length(btrim(name)) between 1 and 80),
  -- scrypt hash with its own salt and parameters; the password itself is never stored.
  password_hash text not null,
  created_at    timestamptz not null default now()
);
create unique index if not exists users_email_key on users (lower(email));

-- Login sessions. The browser holds a random token; only its SHA-256 is stored,
-- so a leaked table cannot be replayed as logins.
create table if not exists sessions (
  token_hash text primary key,
  user_id    bigint not null references users (id) on delete cascade,
  created_at timestamptz not null default now(),
  expires_at timestamptz not null
);
create index if not exists sessions_user_idx on sessions (user_id);

create table if not exists categories (
  id         bigint generated always as identity primary key,
  user_id    bigint not null references users (id) on delete cascade,
  name       text not null check (length(btrim(name)) between 1 and 50),
  type       text not null check (type in ('income', 'expense')),
  created_at timestamptz not null default now(),
  -- Target for the composite foreign keys below: a transaction or budget must
  -- point at a category of the same user and the same type.
  unique (id, user_id, type)
);
-- "Food" and "food" are the same category, per user and type.
create unique index if not exists categories_user_type_name_key on categories (user_id, type, lower(name));

create table if not exists transactions (
  id          bigint generated always as identity primary key,
  user_id     bigint not null references users (id) on delete cascade,
  type        text not null check (type in ('income', 'expense')),
  amount      numeric(12,2) not null check (amount > 0),
  category_id bigint not null,
  date        date not null,
  description text not null default '' check (length(description) <= 200),
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),
  -- RESTRICT: a category with transactions cannot be deleted out from under them.
  foreign key (category_id, user_id, type) references categories (id, user_id, type) on delete restrict
);
create index if not exists transactions_user_date_idx on transactions (user_id, date);
create index if not exists transactions_category_idx on transactions (category_id);

create table if not exists budgets (
  id            bigint generated always as identity primary key,
  user_id       bigint not null references users (id) on delete cascade,
  category_id   bigint not null,
  -- Constant column so the composite key can insist on an expense category.
  category_type text not null default 'expense' check (category_type = 'expense'),
  month         date not null check (extract(day from month) = 1),
  amount        numeric(12,2) not null check (amount > 0),
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now(),
  unique (category_id, month),
  foreign key (category_id, user_id, category_type)
    references categories (id, user_id, type) on delete cascade
);
create index if not exists budgets_user_month_idx on budgets (user_id, month);

-- Savings goals, kept from the original Ledger Savings page.
create table if not exists goals (
  id            bigint generated always as identity primary key,
  user_id       bigint not null references users (id) on delete cascade,
  name          text not null check (length(btrim(name)) between 1 and 80),
  target_amount numeric(12,2) not null check (target_amount > 0),
  target_date   date,
  created_at    timestamptz not null default now(),
  unique (id, user_id)
);
create unique index if not exists goals_user_name_key on goals (user_id, lower(name));

create table if not exists contributions (
  id          bigint generated always as identity primary key,
  user_id     bigint not null,
  goal_id     bigint not null,
  amount      numeric(12,2) not null check (amount > 0),
  date        date not null,
  description text not null default '' check (length(description) <= 200),
  created_at  timestamptz not null default now(),
  foreign key (goal_id, user_id) references goals (id, user_id) on delete cascade
);
create index if not exists contributions_goal_idx on contributions (goal_id);

-- One row per user: the monthly savings target the Savings page measures against.
create table if not exists settings (
  user_id        bigint primary key references users (id) on delete cascade,
  savings_target numeric(12,2) not null default 0 check (savings_target >= 0)
);

-- Row Level Security. Supabase publishes tables in the public schema through
-- its auto-generated REST API, reachable with the browser-safe anon key. RLS
-- with no policies means that API returns nothing and accepts no writes —
-- important now that users and password hashes live here.
-- The FastAPI backend connects as the table owner (postgres) over a direct
-- Postgres connection, which bypasses RLS; it enforces per-user access itself
-- (every query is filtered by the logged-in user's id). See backend/README.md.
alter table users         enable row level security;
alter table sessions      enable row level security;
alter table categories    enable row level security;
alter table transactions  enable row level security;
alter table budgets       enable row level security;
alter table goals         enable row level security;
alter table contributions enable row level security;
alter table settings      enable row level security;

-- No seed rows: each new account gets its default categories and settings row
-- from the API at registration (backend/database.py, DEFAULT_CATEGORIES).
