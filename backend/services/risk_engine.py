"""Deterministic, rule-based risk flags for one month.

These are illustrative dashboard rules for a student project, not financial
advice or an industry standard. Thresholds come from config (BUDGET_WARNING_PCT,
BUDGET_EXCEEDED_PCT) so they can be explained and tested in one place.

Rules
  budget_warning      (warning)   a category has used >= warning % of its budget
                                  but has not gone past the exceeded threshold
  budget_exceeded     (critical)  a category's spending is above exceeded %
                                  (default 100%, i.e. strictly over budget;
                                  exactly 100% is "at limit" -> warning)
  negative_cash_flow  (critical)  expenses > income for the month, including
                                  any spending in a month with zero income
  projected_overspend (warning)   current month only: total spending is still
                                  within the total budget, but the straight-
                                  line pace projects past it by month end
"""

from decimal import Decimal


def _money(n: Decimal) -> str:
    return f"₹{n:,.2f}"


def assess(fig: dict, lines: list[dict], pace: dict, budget_total: Decimal,
           is_current_month: bool) -> list[dict]:
    risks = []

    for line in lines:
        name, util = line["category"], line["utilization_pct"]
        if line["status"] == "exceeded":
            risks.append({
                "code": "budget_exceeded", "severity": "critical",
                "category_id": line["category_id"], "category": name,
                "value": util, "threshold": line["budget"],
                # Says "over by", not a percentage: ₹0.01 over rounds to "100.0%",
                # which reads as on budget.
                "message": f"{name} is over budget by {_money(-line['remaining'])}: "
                           f"{_money(line['spent'])} spent of {_money(line['budget'])}.",
            })
        elif line["status"] == "warning":
            risks.append({
                "code": "budget_warning", "severity": "warning",
                "category_id": line["category_id"], "category": name,
                "value": util, "threshold": line["budget"],
                "message": f"{name} has used {util}% of its {_money(line['budget'])} budget.",
            })

    income, expenses = fig["income"], fig["expenses"]
    if expenses > income:
        message = (
            f"Expenses of {_money(expenses)} with no income recorded this month."
            if income == 0
            else f"Expenses ({_money(expenses)}) exceed income ({_money(income)}) "
                 f"by {_money(expenses - income)}."
        )
        risks.append({
            "code": "negative_cash_flow", "severity": "critical",
            "value": fig["net_cash_flow"], "message": message,
        })

    projected = pace["projected_expenses"]
    if is_current_month and budget_total > 0 and expenses <= budget_total < projected:
        risks.append({
            "code": "projected_overspend", "severity": "warning",
            "value": projected, "threshold": budget_total,
            "message": f"At this pace spending reaches {_money(projected)} by month end, "
                       f"over the {_money(budget_total)} total budget.",
        })

    # Critical first; stable within a severity.
    risks.sort(key=lambda r: r["severity"] != "critical")
    return risks
