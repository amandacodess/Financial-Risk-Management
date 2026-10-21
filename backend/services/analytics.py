"""Pure calculations over aggregated figures. No database, no clock.

Every function takes plain values (Decimals, dates, dicts) and returns plain
values, so the dashboard arithmetic is tested without Supabase.

Definitions used throughout:
  * net_cash_flow = income - expenses recorded for the period. It is NOT a
    bank balance: it knows nothing about money held before the period or
    anything not entered into the ledger.
  * savings_rate_pct = net_cash_flow / income * 100, or None when the period
    has no income (a rate of "minus infinity" means nothing).
  * utilization_pct = spent / budget * 100, or None when there is no budget.
"""

import calendar
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

ZERO = Decimal("0")
CENT = Decimal("0.01")
TENTH = Decimal("0.1")


def parse_month(value: str) -> date:
    """'2026-10' -> date(2026, 10, 1). Raises ValueError on anything else."""
    year, sep, month = value.partition("-")
    if not (sep and len(year) == 4 and len(month) == 2 and year.isdigit() and month.isdigit()
            and 1 <= int(month) <= 12):
        raise ValueError("month must be in YYYY-MM format")
    return date(int(year), int(month), 1)


def add_months(month: date, n: int) -> date:
    index = month.year * 12 + month.month - 1 + n
    return date(index // 12, index % 12 + 1, 1)


def month_range(month: date) -> tuple[date, date]:
    """Half-open [first day, first day of next month)."""
    return month, add_months(month, 1)


def month_key(month: date) -> str:
    return month.strftime("%Y-%m")


def pct(part: Decimal, whole: Decimal) -> Decimal | None:
    if whole <= 0:
        return None
    return (part / whole * 100).quantize(TENTH, ROUND_HALF_UP)


def figures(income: Decimal, expenses: Decimal) -> dict:
    net = income - expenses
    return {
        "income": income,
        "expenses": expenses,
        "net_cash_flow": net,
        "savings_rate_pct": pct(net, income),
    }


def month_totals(rows: list[dict], month: date) -> tuple[Decimal, Decimal, dict[int, dict]]:
    """From aggregate rows, one month's income, expenses and spend per category.

    rows: {month: date, type, category_id, category, amount} grouped by
    month/type/category, as returned by the repository.
    """
    income = expenses = ZERO
    spent: dict[int, dict] = {}
    for r in rows:
        if r["month"] != month:
            continue
        if r["type"] == "income":
            income += r["amount"]
        else:
            expenses += r["amount"]
            line = spent.setdefault(r["category_id"], {"category": r["category"], "amount": ZERO})
            line["amount"] += r["amount"]
    return income, expenses, spent


def budget_status(utilization: Decimal | None, warning_pct: Decimal, exceeded_pct: Decimal) -> str:
    if utilization is None:
        return "no_budget"
    if utilization > exceeded_pct:
        return "exceeded"
    if utilization >= warning_pct:
        return "warning"
    return "ok"


def budget_lines(budgets: list[dict], spent: dict[int, dict],
                 warning_pct: Decimal, exceeded_pct: Decimal) -> list[dict]:
    """Budget vs actual for every category that has a budget or any spending."""
    budget_by_cat = {b["category_id"]: b for b in budgets}
    lines = []
    for cat_id in budget_by_cat.keys() | spent.keys():
        b = budget_by_cat.get(cat_id)
        amount_spent = spent.get(cat_id, {}).get("amount", ZERO)
        budget = b["amount"] if b else None
        # Status from the exact ratio: 79.99% displays as 80.0 but is not a warning.
        exact = amount_spent / budget * 100 if budget else None
        lines.append({
            "category_id": cat_id,
            "category": b["category"] if b else spent[cat_id]["category"],
            "budget": budget,
            "spent": amount_spent,
            "remaining": budget - amount_spent if budget else None,
            "utilization_pct": pct(amount_spent, budget) if budget else None,
            "status": budget_status(exact, warning_pct, exceeded_pct),
        })
    lines.sort(key=lambda l: (-l["spent"], l["category"]))
    return lines


def pace(spent: Decimal, month: date, today: date) -> dict:
    """Straight-line projection of month-end spending from the pace so far.

    A past month is complete (projection = actual); a future month has no
    days elapsed and projects to what is already recorded.
    """
    days_in_month = calendar.monthrange(month.year, month.month)[1]
    if (today.year, today.month) == (month.year, month.month):
        elapsed = today.day
    elif today > month:
        elapsed = days_in_month
    else:
        elapsed = 0
    projected = spent * days_in_month / elapsed if elapsed else spent
    return {
        "days_elapsed": elapsed,
        "days_in_month": days_in_month,
        "projected_expenses": projected.quantize(CENT, ROUND_HALF_UP),
    }


def forecast(rows: list[dict], month: date, lookback: int = 3) -> list[dict]:
    """Per-category average spend over the `lookback` months before `month`.

    Averaged over the months that had any spending at all, so a category
    bought in one of three active months counts as zero in the other two,
    while a ledger with only one month of history is not divided by three.
    """
    start = add_months(month, -lookback)
    window = [r for r in rows if r["type"] == "expense" and start <= r["month"] < month]
    active_months = len({r["month"] for r in window})
    if not active_months:
        return []
    totals: dict[int, dict] = {}
    for r in window:
        line = totals.setdefault(r["category_id"], {"category": r["category"], "amount": ZERO})
        line["amount"] += r["amount"]
    result = [
        {"category_id": cid, "category": t["category"],
         "predicted": (t["amount"] / active_months).quantize(CENT, ROUND_HALF_UP)}
        for cid, t in totals.items()
    ]
    result.sort(key=lambda f: (-f["predicted"], f["category"]))
    return result


def monthly_series(rows: list[dict], end_month: date, count: int) -> list[dict]:
    """Income/expense figures for `count` months ending with `end_month`, oldest first."""
    series = []
    for i in range(count - 1, -1, -1):
        m = add_months(end_month, -i)
        income, expenses, _ = month_totals(rows, m)
        series.append({"month": month_key(m), **figures(income, expenses)})
    return series


def average_savings_rate(series: list[dict]) -> Decimal | None:
    """Mean of the monthly rates, skipping months with no income."""
    rates = [m["savings_rate_pct"] for m in series if m["savings_rate_pct"] is not None]
    if not rates:
        return None
    return (sum(rates) / len(rates)).quantize(TENTH, ROUND_HALF_UP)


def months_between(a: date, b: date) -> int:
    """Whole calendar months from a to b, negative when b is earlier."""
    return (b.year - a.year) * 12 + b.month - a.month


def goal_progress(goal: dict, saved: Decimal, first_contribution: date | None, today: date) -> dict:
    """Ported from the original Go computeGoalProgress.

    pace: complete | none (no deadline) | unknown (deadline, no contributions
    yet) | ahead | behind. A deadline this month or in the past means the
    whole remainder is owed now.
    """
    target = goal["target_amount"]
    remaining = max(ZERO, target - saved)
    observed = None
    if first_contribution is not None:
        funding_months = max(1, months_between(first_contribution, today) + 1)
        observed = (saved / funding_months).quantize(CENT, ROUND_HALF_UP)

    months_left = required = None
    if goal["target_date"] is not None:
        months_left = max(0, months_between(today, goal["target_date"]))

    if saved >= target:
        status = "complete"
    elif months_left is None:
        status = "none"
    elif months_left == 0:
        required, status = remaining, "behind"
    else:
        required = (remaining / months_left).quantize(CENT, ROUND_HALF_UP)
        if observed is None:
            status = "unknown"
        else:
            status = "ahead" if observed >= required else "behind"

    return {
        **goal,
        "saved": saved,
        "remaining": remaining,
        "percent_complete": min(Decimal(100), pct(saved, target) or ZERO),
        "months_left": months_left,
        "required_per_month": required,
        "observed_per_month": observed,
        "pace": status,
    }
