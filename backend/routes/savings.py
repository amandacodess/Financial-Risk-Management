"""Savings goals and the savings target, kept from the original Ledger Savings page."""

from datetime import date

from fastapi import APIRouter, Depends, Response

from config import get_today
from auth import user_id
from database import get_repo
from schemas import ContributionIn, ContributionOut, GoalIn, GoalOut, SettingsIn, SettingsOut
from services.analytics import ZERO, goal_progress

router = APIRouter(prefix="/api", tags=["savings"])


@router.get("/goals", response_model=list[GoalOut])
def list_goals(uid: int = Depends(user_id), repo=Depends(get_repo), today: date = Depends(get_today)):
    """Each goal with its progress and pace verdict."""
    result = []
    for row in repo.list_goals(uid):
        goal = {k: row[k] for k in ("id", "name", "target_amount", "target_date")}
        result.append(goal_progress(goal, row["saved"], row["first_contribution"], today))
    return result


@router.post("/goals", response_model=GoalOut, status_code=201)
def create_goal(body: GoalIn, uid: int = Depends(user_id), repo=Depends(get_repo),
                today: date = Depends(get_today)):
    row = repo.create_goal(uid, body.model_dump())
    return goal_progress(row, ZERO, None, today)


@router.delete("/goals/{id}", status_code=204)
def delete_goal(id: int, uid: int = Depends(user_id), repo=Depends(get_repo)):
    """Deletes the goal and, by cascade, its contributions."""
    repo.delete_goal(uid, id)
    return Response(status_code=204)


@router.post("/goals/{id}/contributions", response_model=ContributionOut, status_code=201)
def add_contribution(id: int, body: ContributionIn, uid: int = Depends(user_id),
                     repo=Depends(get_repo)):
    return repo.add_contribution(uid, id, body.model_dump())


@router.get("/settings", response_model=SettingsOut)
def get_settings(uid: int = Depends(user_id), repo=Depends(get_repo)):
    return repo.get_settings(uid)


@router.put("/settings", response_model=SettingsOut)
def update_settings(body: SettingsIn, uid: int = Depends(user_id), repo=Depends(get_repo)):
    return repo.update_settings(uid, body.savings_target)
