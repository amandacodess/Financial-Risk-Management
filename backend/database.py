"""PostgreSQL access: one repository class, plain SQL, psycopg 3 connection pool.

Why a direct Postgres connection rather than the supabase-py client: the
dashboard needs GROUP BY aggregates and composite-key constraint errors, which
are one SQL statement each here but awkward through Supabase's REST layer; it
also keeps the service-role key out of the picture entirely. Supabase is still
the host; we just speak Postgres to it.

Every data method takes the logged-in user's id and filters on it. A record
that belongs to someone else is indistinguishable from one that does not
exist (404), so ids reveal nothing about other accounts.

Routes receive the repository through the get_repo dependency, so tests swap
in an in-memory fake (tests/fakes.py) without touching any database.
"""

from contextlib import contextmanager
from datetime import date, datetime

import psycopg
from fastapi import Request
from psycopg import errors as pg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool, PoolTimeout

# Every new account starts with these (the original Ledger's, plus income ones).
DEFAULT_CATEGORIES = [
    ("Food", "expense"), ("Transport", "expense"), ("Shopping", "expense"),
    ("Bills", "expense"), ("Entertainment", "expense"), ("Health", "expense"),
    ("Other", "expense"),
    ("Salary", "income"), ("Freelance", "income"), ("Other income", "income"),
]


class NotFound(Exception):
    pass


class Conflict(Exception):
    pass


class InvalidReference(Exception):
    pass


class Unavailable(Exception):
    pass


_TX_COLUMNS = "t.id, t.type, t.amount, t.category_id, c.name AS category, t.date, t.description"
_USER_COLUMNS = "id, name, email, created_at"


class PostgresRepository:
    def __init__(self, conninfo: str, timeout: float = 10):
        self.pool = ConnectionPool(
            conninfo,
            min_size=1,
            max_size=5,
            timeout=timeout,
            open=False,
            # prepare_threshold=None: Supabase's transaction pooler cannot
            # keep prepared statements between transactions.
            kwargs={"row_factory": dict_row, "prepare_threshold": None},
            # Test each connection before lending it out. Supabase's pooler closes
            # idle connections; without this, the first request after a quiet
            # spell fails with "Database unavailable" instead of reconnecting.
            check=ConnectionPool.check_connection,
        )

    def open(self):
        self.pool.open(wait=False)

    def close(self):
        self.pool.close()

    @contextmanager
    def _conn(self):
        """One connection, one transaction: committed on success, rolled back on error."""
        try:
            with self.pool.connection() as conn:
                yield conn
        except (PoolTimeout, psycopg.OperationalError) as e:
            raise Unavailable("Database unavailable") from e

    def _run(self, sql: str, params=(), fetch: str | None = "all", on: dict | None = None):
        """Execute one statement in its own transaction.

        `on` maps constraint-error classes to the domain error to raise
        instead, so callers say what a violation *means* for that operation.
        """
        try:
            with self._conn() as conn:
                cur = conn.execute(sql, params)
                if fetch == "all":
                    return cur.fetchall()
                if fetch == "one":
                    return cur.fetchone()
                return cur.rowcount
        except psycopg.IntegrityError as e:
            for error_type, replacement in (on or {}).items():
                if isinstance(e, error_type):
                    raise replacement from None
            raise

    def ping(self) -> None:
        self._run("SELECT 1", fetch="one")

    # --- accounts and sessions -----------------------------------------------

    def create_user(self, name: str, email: str, password_hash: str) -> dict:
        """The user, their default categories and their settings row, atomically."""
        try:
            with self._conn() as conn:
                user = conn.execute(
                    f"INSERT INTO users (name, email, password_hash) VALUES (%s, %s, %s) "
                    f"RETURNING {_USER_COLUMNS}",
                    (name, email, password_hash),
                ).fetchone()
                with conn.cursor() as cur:
                    cur.executemany(
                        "INSERT INTO categories (user_id, name, type) VALUES (%s, %s, %s)",
                        [(user["id"], n, t) for n, t in DEFAULT_CATEGORIES],
                    )
                conn.execute("INSERT INTO settings (user_id) VALUES (%s)", (user["id"],))
                return user
        except pg.UniqueViolation:
            raise Conflict("An account with that email already exists") from None

    def get_user_for_login(self, email: str) -> dict | None:
        return self._run(
            f"SELECT {_USER_COLUMNS}, password_hash FROM users WHERE lower(email) = lower(%s)",
            (email,), fetch="one",
        )

    def create_session(self, token_hash: str, user_id: int, expires_at: datetime) -> None:
        with self._conn() as conn:
            # Housekeeping: a user's expired sessions go whenever they log in again.
            conn.execute("DELETE FROM sessions WHERE user_id = %s AND expires_at < now()", (user_id,))
            conn.execute(
                "INSERT INTO sessions (token_hash, user_id, expires_at) VALUES (%s, %s, %s)",
                (token_hash, user_id, expires_at),
            )

    def get_session_user(self, token_hash: str) -> dict | None:
        return self._run(
            """SELECT u.id, u.name, u.email, u.created_at
               FROM sessions s JOIN users u ON u.id = s.user_id
               WHERE s.token_hash = %s AND s.expires_at > now()""",
            (token_hash,), fetch="one",
        )

    def delete_session(self, token_hash: str) -> None:
        self._run("DELETE FROM sessions WHERE token_hash = %s", (token_hash,), fetch=None)

    # --- categories ----------------------------------------------------------

    def list_categories(self, user_id: int, type: str | None = None) -> list[dict]:
        return self._run(
            """SELECT c.id, c.name, c.type, COUNT(t.id)::int AS transaction_count
               FROM categories c LEFT JOIN transactions t ON t.category_id = c.id
               WHERE c.user_id = %(uid)s AND (%(type)s::text IS NULL OR c.type = %(type)s)
               GROUP BY c.id ORDER BY c.type, c.name""",
            {"uid": user_id, "type": type},
        )

    def create_category(self, user_id: int, name: str, type: str) -> dict:
        row = self._run(
            "INSERT INTO categories (user_id, name, type) VALUES (%s, %s, %s) RETURNING id, name, type",
            (user_id, name, type), fetch="one",
            on={pg.UniqueViolation: Conflict(f"An {type} category with that name already exists")},
        )
        return {**row, "transaction_count": 0}

    def delete_category(self, user_id: int, id: int) -> None:
        n = self._run(
            "DELETE FROM categories WHERE id = %s AND user_id = %s", (id, user_id), fetch=None,
            # ON DELETE RESTRICT raises restrict_violation (23001), not foreign_key_violation.
            on={pg.RestrictViolation: Conflict("Category is used by existing transactions")},
        )
        if n == 0:
            raise NotFound("Category not found")

    # --- transactions --------------------------------------------------------

    def list_transactions(self, user_id: int, start: date | None = None, end: date | None = None,
                          type: str | None = None, category_id: int | None = None) -> list[dict]:
        return self._run(
            f"""SELECT {_TX_COLUMNS} FROM transactions t JOIN categories c ON c.id = t.category_id
                WHERE t.user_id = %(uid)s
                  AND (%(start)s::date IS NULL OR t.date >= %(start)s)
                  AND (%(end)s::date IS NULL OR t.date < %(end)s)
                  AND (%(type)s::text IS NULL OR t.type = %(type)s)
                  AND (%(cat)s::bigint IS NULL OR t.category_id = %(cat)s)
                ORDER BY t.date DESC, t.id DESC""",
            {"uid": user_id, "start": start, "end": end, "type": type, "cat": category_id},
        )

    def _bad_category(self, type: str) -> dict:
        # The composite key (category_id, user_id, type) also catches another
        # user's category, which reads to the client as "does not exist".
        return {pg.ForeignKeyViolation: InvalidReference(
            f"category_id does not exist or is not an {type} category")}

    def create_transaction(self, user_id: int, data: dict) -> dict:
        return self._run(
            f"""WITH t AS (
                  INSERT INTO transactions (user_id, type, amount, category_id, date, description)
                  VALUES (%(uid)s, %(type)s, %(amount)s, %(category_id)s, %(date)s, %(description)s)
                  RETURNING *)
                SELECT {_TX_COLUMNS} FROM t JOIN categories c ON c.id = t.category_id""",
            {**data, "uid": user_id}, fetch="one", on=self._bad_category(data["type"]),
        )

    def update_transaction(self, user_id: int, id: int, data: dict) -> dict:
        row = self._run(
            f"""WITH t AS (
                  UPDATE transactions SET type = %(type)s, amount = %(amount)s,
                    category_id = %(category_id)s, date = %(date)s,
                    description = %(description)s, updated_at = now()
                  WHERE id = %(id)s AND user_id = %(uid)s RETURNING *)
                SELECT {_TX_COLUMNS} FROM t JOIN categories c ON c.id = t.category_id""",
            {**data, "id": id, "uid": user_id}, fetch="one", on=self._bad_category(data["type"]),
        )
        if row is None:
            raise NotFound("Transaction not found")
        return row

    def delete_transaction(self, user_id: int, id: int) -> None:
        if self._run("DELETE FROM transactions WHERE id = %s AND user_id = %s",
                     (id, user_id), fetch=None) == 0:
            raise NotFound("Transaction not found")

    def aggregate(self, user_id: int, start: date, end: date) -> list[dict]:
        """Totals grouped by month, type and category over [start, end)."""
        return self._run(
            """SELECT date_trunc('month', t.date)::date AS month, t.type,
                      t.category_id, c.name AS category, SUM(t.amount) AS amount
               FROM transactions t JOIN categories c ON c.id = t.category_id
               WHERE t.user_id = %s AND t.date >= %s AND t.date < %s
               GROUP BY 1, 2, 3, 4""",
            (user_id, start, end),
        )

    # --- budgets -------------------------------------------------------------

    _BUDGET_SELECT = """SELECT b.id, b.category_id, c.name AS category, b.month, b.amount
                        FROM b JOIN categories c ON c.id = b.category_id"""

    def list_budgets(self, user_id: int, month: date | None = None) -> list[dict]:
        return self._run(
            """SELECT b.id, b.category_id, c.name AS category, b.month, b.amount
               FROM budgets b JOIN categories c ON c.id = b.category_id
               WHERE b.user_id = %(uid)s AND (%(month)s::date IS NULL OR b.month = %(month)s)
               ORDER BY b.month DESC, c.name""",
            {"uid": user_id, "month": month},
        )

    def create_budget(self, user_id: int, category_id: int, month: date, amount) -> dict:
        return self._run(
            f"""WITH b AS (INSERT INTO budgets (user_id, category_id, month, amount)
                           VALUES (%s, %s, %s, %s) RETURNING *)
                {self._BUDGET_SELECT}""",
            (user_id, category_id, month, amount), fetch="one",
            on={
                pg.UniqueViolation: Conflict("A budget for this category and month already exists"),
                pg.ForeignKeyViolation: InvalidReference(
                    "category_id does not exist or is not an expense category"),
            },
        )

    def update_budget(self, user_id: int, id: int, amount) -> dict:
        row = self._run(
            f"""WITH b AS (UPDATE budgets SET amount = %s, updated_at = now()
                           WHERE id = %s AND user_id = %s RETURNING *)
                {self._BUDGET_SELECT}""",
            (amount, id, user_id), fetch="one",
        )
        if row is None:
            raise NotFound("Budget not found")
        return row

    def delete_budget(self, user_id: int, id: int) -> None:
        if self._run("DELETE FROM budgets WHERE id = %s AND user_id = %s",
                     (id, user_id), fetch=None) == 0:
            raise NotFound("Budget not found")

    # --- savings goals -------------------------------------------------------

    def list_goals(self, user_id: int) -> list[dict]:
        return self._run(
            """SELECT g.id, g.name, g.target_amount, g.target_date,
                      COALESCE(SUM(k.amount), 0) AS saved, MIN(k.date) AS first_contribution
               FROM goals g LEFT JOIN contributions k ON k.goal_id = g.id
               WHERE g.user_id = %s
               GROUP BY g.id ORDER BY g.name""",
            (user_id,),
        )

    def create_goal(self, user_id: int, data: dict) -> dict:
        return self._run(
            """INSERT INTO goals (user_id, name, target_amount, target_date)
               VALUES (%(uid)s, %(name)s, %(target_amount)s, %(target_date)s)
               RETURNING id, name, target_amount, target_date""",
            {**data, "uid": user_id}, fetch="one",
            on={pg.UniqueViolation: Conflict("A goal with that name already exists")},
        )

    def delete_goal(self, user_id: int, id: int) -> None:
        if self._run("DELETE FROM goals WHERE id = %s AND user_id = %s", (id, user_id), fetch=None) == 0:
            raise NotFound("Goal not found")

    def add_contribution(self, user_id: int, goal_id: int, data: dict) -> dict:
        return self._run(
            """INSERT INTO contributions (user_id, goal_id, amount, date, description)
               VALUES (%(uid)s, %(goal_id)s, %(amount)s, %(date)s, %(description)s)
               RETURNING id, goal_id, amount, date, description""",
            {**data, "goal_id": goal_id, "uid": user_id}, fetch="one",
            # (goal_id, user_id) must match one of this user's goals.
            on={pg.ForeignKeyViolation: NotFound("Goal not found")},
        )

    # --- settings ------------------------------------------------------------

    def get_settings(self, user_id: int) -> dict:
        return self._run("SELECT savings_target FROM settings WHERE user_id = %s",
                         (user_id,), fetch="one")

    def update_settings(self, user_id: int, savings_target) -> dict:
        return self._run(
            "UPDATE settings SET savings_target = %s WHERE user_id = %s RETURNING savings_target",
            (savings_target, user_id), fetch="one",
        )


def get_repo(request: Request):
    repo = request.app.state.repo
    if repo is None:
        raise Unavailable("Database is not configured (set DATABASE_URL)")
    return repo
