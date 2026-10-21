from fastapi import APIRouter, Depends, Query, Response

from auth import user_id
from database import get_repo
from routes import month_query
from schemas import BudgetIn, BudgetOut, BudgetUpdate
from services.analytics import month_key

router = APIRouter(prefix="/api/budgets", tags=["budgets"])


def _out(row: dict) -> dict:
    return {**row, "month": month_key(row["month"])}


@router.get("", response_model=list[BudgetOut])
def list_budgets(month: str | None = Query(None, description="YYYY-MM; omit for all"),
                 uid: int = Depends(user_id), repo=Depends(get_repo)):
    return [_out(r) for r in repo.list_budgets(uid, month_query(month))]


@router.post("", response_model=BudgetOut, status_code=201)
def create_budget(body: BudgetIn, uid: int = Depends(user_id), repo=Depends(get_repo)):
    """One budget per expense category per month; a second one is a 409."""
    return _out(repo.create_budget(uid, body.category_id, body.month, body.amount))


@router.put("/{id}", response_model=BudgetOut)
def update_budget(id: int, body: BudgetUpdate, uid: int = Depends(user_id), repo=Depends(get_repo)):
    return _out(repo.update_budget(uid, id, body.amount))


@router.delete("/{id}", status_code=204)
def delete_budget(id: int, uid: int = Depends(user_id), repo=Depends(get_repo)):
    repo.delete_budget(uid, id)
    return Response(status_code=204)
