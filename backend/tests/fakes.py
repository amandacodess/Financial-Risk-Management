"""In-memory stand-in for PostgresRepository, used by the unit tests.

It mirrors the constraints in sql/schema.sql that the API relies on (per-user
ownership, category type matching, unique budgets per category+month,
restricted category delete, goal cascade, unique emails) by raising the same
domain errors the real repository raises. The integration tests in
test_integration.py check the real SQL does too.
"""

from collections import defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal

from database import DEFAULT_CATEGORIES, Conflict, InvalidReference, NotFound, Unavailable


class FakeRepository:
    def __init__(self):
        self.users: dict[int, dict] = {}
        self.sessions: dict[str, dict] = {}
        self.categories: dict[int, dict] = {}
        self.transactions: dict[int, dict] = {}
        self.budgets: dict[int, dict] = {}
        self.goals: dict[int, dict] = {}
        self.contributions: dict[int, dict] = {}
        self.settings: dict[int, dict] = {}
        self._next = 0

    def _id(self) -> int:
        self._next += 1
        return self._next

    def category_id(self, name: str, user_id: int | None = None) -> int:
        """Test helper: a category id by name, for the first user unless told otherwise."""
        uid = user_id if user_id is not None else min(self.users)
        return next(c["id"] for c in self.categories.values() if c["name"] == name and c["user_id"] == uid)

    def ping(self):
        pass

    # --- accounts and sessions -----------------------------------------------

    def create_user(self, name, email, password_hash):
        if any(u["email"].lower() == email.lower() for u in self.users.values()):
            raise Conflict("An account with that email already exists")
        u = {"id": self._id(), "name": name, "email": email, "password_hash": password_hash,
             "created_at": datetime.now(timezone.utc)}
        self.users[u["id"]] = u
        for cname, ctype in DEFAULT_CATEGORIES:
            c = {"id": self._id(), "user_id": u["id"], "name": cname, "type": ctype}
            self.categories[c["id"]] = c
        self.settings[u["id"]] = {"savings_target": Decimal("0")}
        return {k: v for k, v in u.items() if k != "password_hash"}

    def get_user_for_login(self, email):
        return next((dict(u) for u in self.users.values() if u["email"].lower() == email.lower()), None)

    def create_session(self, token_hash, user_id, expires_at):
        self.sessions[token_hash] = {"user_id": user_id, "expires_at": expires_at}

    def get_session_user(self, token_hash):
        s = self.sessions.get(token_hash)
        if s is None or s["expires_at"] <= datetime.now(timezone.utc):
            return None
        u = self.users[s["user_id"]]
        return {k: v for k, v in u.items() if k != "password_hash"}

    def delete_session(self, token_hash):
        self.sessions.pop(token_hash, None)

    # --- categories ----------------------------------------------------------

    def list_categories(self, user_id, type=None):
        counts = defaultdict(int)
        for t in self.transactions.values():
            counts[t["category_id"]] += 1
        return sorted(
            ({"id": c["id"], "name": c["name"], "type": c["type"], "transaction_count": counts[c["id"]]}
             for c in self.categories.values()
             if c["user_id"] == user_id and (type is None or c["type"] == type)),
            key=lambda c: (c["type"], c["name"]),
        )

    def create_category(self, user_id, name, type):
        if any(c["user_id"] == user_id and c["type"] == type and c["name"].lower() == name.lower()
               for c in self.categories.values()):
            raise Conflict(f"An {type} category with that name already exists")
        c = {"id": self._id(), "user_id": user_id, "name": name, "type": type}
        self.categories[c["id"]] = c
        return {"id": c["id"], "name": name, "type": type, "transaction_count": 0}

    def delete_category(self, user_id, id):
        c = self.categories.get(id)
        if c is None or c["user_id"] != user_id:
            raise NotFound("Category not found")
        if any(t["category_id"] == id for t in self.transactions.values()):
            raise Conflict("Category is used by existing transactions")
        del self.categories[id]
        self.budgets = {k: b for k, b in self.budgets.items() if b["category_id"] != id}

    # --- transactions --------------------------------------------------------

    def _tx_out(self, t):
        return {k: v for k, v in t.items() if k != "user_id"} | {
            "category": self.categories[t["category_id"]]["name"]}

    def _check_category(self, user_id, data):
        c = self.categories.get(data["category_id"])
        if c is None or c["type"] != data["type"] or c["user_id"] != user_id:
            raise InvalidReference(
                f"category_id does not exist or is not an {data['type']} category")

    def _own(self, table, user_id, id, what):
        row = table.get(id)
        if row is None or row["user_id"] != user_id:
            raise NotFound(f"{what} not found")
        return row

    def list_transactions(self, user_id, start=None, end=None, type=None, category_id=None):
        rows = [
            t for t in self.transactions.values()
            if t["user_id"] == user_id
            and (start is None or t["date"] >= start) and (end is None or t["date"] < end)
            and (type is None or t["type"] == type)
            and (category_id is None or t["category_id"] == category_id)
        ]
        rows.sort(key=lambda t: (t["date"], t["id"]), reverse=True)
        return [self._tx_out(t) for t in rows]

    def create_transaction(self, user_id, data):
        self._check_category(user_id, data)
        t = {"id": self._id(), "user_id": user_id, **data}
        self.transactions[t["id"]] = t
        return self._tx_out(t)

    def update_transaction(self, user_id, id, data):
        self._own(self.transactions, user_id, id, "Transaction")
        self._check_category(user_id, data)
        self.transactions[id] = {"id": id, "user_id": user_id, **data}
        return self._tx_out(self.transactions[id])

    def delete_transaction(self, user_id, id):
        self._own(self.transactions, user_id, id, "Transaction")
        del self.transactions[id]

    def aggregate(self, user_id, start, end):
        totals = defaultdict(Decimal)
        for t in self.transactions.values():
            if t["user_id"] == user_id and start <= t["date"] < end:
                totals[(t["date"].replace(day=1), t["type"], t["category_id"])] += t["amount"]
        return [
            {"month": m, "type": ty, "category_id": cid,
             "category": self.categories[cid]["name"], "amount": amount}
            for (m, ty, cid), amount in totals.items()
        ]

    # --- budgets -------------------------------------------------------------

    def _budget_out(self, b):
        return {k: v for k, v in b.items() if k != "user_id"} | {
            "category": self.categories[b["category_id"]]["name"]}

    def list_budgets(self, user_id, month=None):
        return [self._budget_out(b) for b in self.budgets.values()
                if b["user_id"] == user_id and (month is None or b["month"] == month)]

    def create_budget(self, user_id, category_id, month, amount):
        c = self.categories.get(category_id)
        if c is None or c["type"] != "expense" or c["user_id"] != user_id:
            raise InvalidReference("category_id does not exist or is not an expense category")
        if any(b["category_id"] == category_id and b["month"] == month for b in self.budgets.values()):
            raise Conflict("A budget for this category and month already exists")
        b = {"id": self._id(), "user_id": user_id, "category_id": category_id, "month": month, "amount": amount}
        self.budgets[b["id"]] = b
        return self._budget_out(b)

    def update_budget(self, user_id, id, amount):
        self._own(self.budgets, user_id, id, "Budget")["amount"] = amount
        return self._budget_out(self.budgets[id])

    def delete_budget(self, user_id, id):
        self._own(self.budgets, user_id, id, "Budget")
        del self.budgets[id]

    # --- goals and settings --------------------------------------------------

    def list_goals(self, user_id):
        result = []
        for g in sorted((g for g in self.goals.values() if g["user_id"] == user_id), key=lambda g: g["name"]):
            mine = [k for k in self.contributions.values() if k["goal_id"] == g["id"]]
            result.append({
                **{k: v for k, v in g.items() if k != "user_id"},
                "saved": sum((k["amount"] for k in mine), Decimal("0")),
                "first_contribution": min((k["date"] for k in mine), default=None),
            })
        return result

    def create_goal(self, user_id, data):
        if any(g["user_id"] == user_id and g["name"].lower() == data["name"].lower()
               for g in self.goals.values()):
            raise Conflict("A goal with that name already exists")
        g = {"id": self._id(), "user_id": user_id, **data}
        self.goals[g["id"]] = g
        return {k: v for k, v in g.items() if k != "user_id"}

    def delete_goal(self, user_id, id):
        self._own(self.goals, user_id, id, "Goal")
        del self.goals[id]
        self.contributions = {k: c for k, c in self.contributions.items() if c["goal_id"] != id}

    def add_contribution(self, user_id, goal_id, data):
        self._own(self.goals, user_id, goal_id, "Goal")
        k = {"id": self._id(), "goal_id": goal_id, **data}
        self.contributions[k["id"]] = k
        return dict(k)

    def get_settings(self, user_id):
        return dict(self.settings[user_id])

    def update_settings(self, user_id, savings_target):
        self.settings[user_id]["savings_target"] = savings_target
        return dict(self.settings[user_id])


class DownRepository:
    """Every call fails the way an unreachable database does."""

    def __getattr__(self, name):
        def fail(*args, **kwargs):
            raise Unavailable("Database unavailable")
        return fail


class BrokenRepository:
    """Every call fails with an unexpected internal error."""

    def __getattr__(self, name):
        def fail(*args, **kwargs):
            raise RuntimeError("password=FAKE-NOT-A-SECRET host=db.internal")  # must never reach the client
        return fail


def tx(type="expense", amount="100.00", category_id=None, on="2026-10-05", description=""):
    """JSON body for a transaction, as the frontend would send it."""
    return {"type": type, "amount": amount, "category_id": category_id,
            "date": on, "description": description}


PASSWORD = "correct horse battery"  # fictional test password


def register(client, name="Asha Test", email="asha@example.com") -> dict:
    """Create an account through the API; returns the Authorization header for it."""
    r = client.post("/api/auth/register", json={"name": name, "email": email, "password": PASSWORD})
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


TODAY = date(2026, 10, 20)
