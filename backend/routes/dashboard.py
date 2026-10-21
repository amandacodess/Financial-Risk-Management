"""Read-only figures: dashboard summary, monthly analytics, risk flags.

The routes only fetch aggregates and hand them to services/, where all the
arithmetic and the risk rules live (and are unit-tested without a database).
"""

from datetime import date

from fastapi import APIRouter, Depends, Query

from config import Config, get_config, get_today
from auth import user_id
from database import get_repo
from routes import month_query
from schemas import MonthlyAnalytics, RiskReport, Summary
from services import analytics as a
from services.risk_engine import assess

router = APIRouter(prefix="/api", tags=["dashboard"])

MonthParam = Query(None, description="YYYY-MM; defaults to the current month in APP_TZ")


def month_report(repo, uid: int, config: Config, month: date, today: date) -> dict:
    # Three months before the selected one feed the forecast.
    rows = repo.aggregate(uid, a.add_months(month, -3), a.add_months(month, 1))
    income, expenses, spent = a.month_totals(rows, month)
    fig = a.figures(income, expenses)
    budgets = repo.list_budgets(uid, month)
    lines = a.budget_lines(budgets, spent, config.budget_warning_pct, config.budget_exceeded_pct)
    budget_total = sum((b["amount"] for b in budgets), a.ZERO)
    pace = a.pace(expenses, month, today)
    is_current = (month.year, month.month) == (today.year, today.month)
    return {
        "month": a.month_key(month),
        **fig,
        "budget_total": budget_total,
        "budget_utilization_pct": a.pct(expenses, budget_total),
        "categories": lines,
        "pace": pace,
        "forecast": a.forecast(rows, month),
        "risks": assess(fig, lines, pace, budget_total, is_current),
    }


def _this_month(today: date) -> date:
    return date(today.year, today.month, 1)


@router.get("/dashboard/summary", response_model=Summary)
def summary(month: str | None = MonthParam, uid: int = Depends(user_id), repo=Depends(get_repo),
            config: Config = Depends(get_config), today: date = Depends(get_today)):
    """Income, expenses, net cash flow, savings rate, budget vs actual and risks for one month."""
    return month_report(repo, uid, config, month_query(month, _this_month(today)), today)


@router.get("/risks", response_model=RiskReport)
def risks(month: str | None = MonthParam, uid: int = Depends(user_id), repo=Depends(get_repo),
          config: Config = Depends(get_config), today: date = Depends(get_today)):
    """Just the risk flags from the summary, critical first."""
    report = month_report(repo, uid, config, month_query(month, _this_month(today)), today)
    return {"month": report["month"], "risks": report["risks"]}


@router.get("/analytics/monthly", response_model=MonthlyAnalytics)
def monthly(months: int = Query(6, ge=1, le=24, description="How many months to return"),
            end: str | None = Query(None, description="Last month, YYYY-MM; defaults to current"),
            uid: int = Depends(user_id), repo=Depends(get_repo), today: date = Depends(get_today)):
    """Income, expenses, net cash flow and savings rate per month, oldest first."""
    end_month = month_query(end, _this_month(today))
    rows = repo.aggregate(uid, a.add_months(end_month, -(months - 1)), a.add_months(end_month, 1))
    series = a.monthly_series(rows, end_month, months)
    return {"months": series, "average_savings_rate_pct": a.average_savings_rate(series)}
