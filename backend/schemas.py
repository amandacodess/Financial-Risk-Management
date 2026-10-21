"""Request and response models.

Money is Decimal end to end on the server and is sent to the browser as a JSON
number (two decimal places at most), because the Ledger frontend does
arithmetic on these values and a JSON string would concatenate instead of add.
"""

import re
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, BeforeValidator, ConfigDict, Field, PlainSerializer, StringConstraints

from services.analytics import parse_month

TxType = Literal["income", "expense"]

# JSON-number output for any Decimal figure (amounts, percentages).
Num = Annotated[Decimal, PlainSerializer(float, return_type=float, when_used="json")]
# Validated input amount: positive, at most 2 decimal places, below 10 billion.
Amount = Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=2)]
def _iso_date(value):
    # Only "YYYY-MM-DD" strings: pydantic would otherwise also accept Unix
    # timestamps and datetimes. Impossible dates (2026-02-30) still fail
    # pydantic's own date parsing afterwards.
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError("date must be in YYYY-MM-DD format")
    return value


StrictDate = Annotated[date, BeforeValidator(_iso_date)]
# "YYYY-MM" in, first-of-month date out.
Month = Annotated[str, AfterValidator(parse_month)]
Text = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]


class Input(BaseModel):
    # Unknown fields are refused, so a typo like "ammount" is an error, not a silent no-op.
    model_config = ConfigDict(extra="forbid")


# --- categories --------------------------------------------------------------

class CategoryIn(Input):
    name: Name
    type: TxType


class CategoryOut(BaseModel):
    id: int
    name: str
    type: TxType
    transaction_count: int = 0


# --- transactions ------------------------------------------------------------

class TransactionIn(Input):
    type: TxType
    amount: Amount
    category_id: int = Field(gt=0)
    date: StrictDate
    description: Text = ""


class TransactionOut(BaseModel):
    id: int
    type: TxType
    amount: Num
    category_id: int
    category: str
    date: date
    description: str


# --- budgets -----------------------------------------------------------------

class BudgetIn(Input):
    category_id: int = Field(gt=0)
    month: Month
    amount: Amount


class BudgetUpdate(Input):
    amount: Amount


class BudgetOut(BaseModel):
    id: int
    category_id: int
    category: str
    month: str
    amount: Num


# --- dashboard, analytics, risks --------------------------------------------

class Risk(BaseModel):
    code: Literal["budget_warning", "budget_exceeded", "negative_cash_flow", "projected_overspend"]
    severity: Literal["warning", "critical"]
    message: str
    category_id: int | None = None
    category: str | None = None
    value: Num | None = None
    threshold: Num | None = None


class CategoryBudgetLine(BaseModel):
    category_id: int
    category: str
    budget: Num | None
    spent: Num
    remaining: Num | None
    utilization_pct: Num | None
    status: Literal["no_budget", "ok", "warning", "exceeded"]


class Pace(BaseModel):
    days_elapsed: int
    days_in_month: int
    projected_expenses: Num


class ForecastLine(BaseModel):
    category_id: int
    category: str
    predicted: Num


class Summary(BaseModel):
    month: str
    income: Num
    expenses: Num
    net_cash_flow: Num
    savings_rate_pct: Num | None
    budget_total: Num
    budget_utilization_pct: Num | None
    categories: list[CategoryBudgetLine]
    pace: Pace
    forecast: list[ForecastLine]
    risks: list[Risk]


class MonthFigures(BaseModel):
    month: str
    income: Num
    expenses: Num
    net_cash_flow: Num
    savings_rate_pct: Num | None


class MonthlyAnalytics(BaseModel):
    months: list[MonthFigures]
    average_savings_rate_pct: Num | None


class RiskReport(BaseModel):
    month: str
    risks: list[Risk]


# --- savings goals -----------------------------------------------------------

class GoalIn(Input):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
    target_amount: Amount
    target_date: StrictDate | None = None


class ContributionIn(Input):
    amount: Amount
    date: StrictDate
    description: Text = ""


class ContributionOut(BaseModel):
    id: int
    goal_id: int
    amount: Num
    date: date
    description: str


class GoalOut(BaseModel):
    id: int
    name: str
    target_amount: Num
    target_date: date | None
    saved: Num
    remaining: Num
    percent_complete: Num
    months_left: int | None
    required_per_month: Num | None
    observed_per_month: Num | None
    pace: Literal["complete", "none", "unknown", "ahead", "behind"]


class SettingsIn(Input):
    savings_target: Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=2)]


class SettingsOut(BaseModel):
    savings_target: Num


# --- accounts ----------------------------------------------------------------

def _email(value: str) -> str:
    # Deliberately simple: one @, something either side, a dot in the domain.
    # Real proof of ownership would need a confirmation email (out of scope).
    value = value.strip().lower()
    if len(value) > 254 or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
        raise ValueError("enter a valid email address")
    return value


Email = Annotated[str, AfterValidator(_email)]
# Length only: long passphrases beat composition rules. 128 caps hashing cost.
Password = Annotated[str, StringConstraints(min_length=8, max_length=128)]


class RegisterIn(Input):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
    email: Email
    password: Password


class LoginIn(Input):
    email: Email
    # No length rule here: a wrong password should get the same answer as any other.
    password: Annotated[str, StringConstraints(min_length=1, max_length=128)]


class UserOut(BaseModel):
    id: int
    name: str
    email: str


class AuthOut(BaseModel):
    token: str
    user: UserOut
