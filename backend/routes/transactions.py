from fastapi import APIRouter, Depends, Query, Response

from auth import user_id
from database import get_repo
from routes import month_query
from schemas import TransactionIn, TransactionOut, TxType
from services.analytics import month_range

router = APIRouter(prefix="/api/transactions", tags=["transactions"])


@router.get("", response_model=list[TransactionOut])
def list_transactions(
    month: str | None = Query(None, description="YYYY-MM; omit for all months"),
    type: TxType | None = None,
    category_id: int | None = Query(None, gt=0),
    uid: int = Depends(user_id),
    repo=Depends(get_repo),
):
    """Newest first. Filters combine: e.g. ?month=2026-10&type=expense."""
    m = month_query(month)
    start, end = month_range(m) if m else (None, None)
    return repo.list_transactions(uid, start, end, type, category_id)


@router.post("", response_model=TransactionOut, status_code=201)
def create_transaction(body: TransactionIn, uid: int = Depends(user_id), repo=Depends(get_repo)):
    return repo.create_transaction(uid, body.model_dump())


@router.put("/{id}", response_model=TransactionOut)
def update_transaction(id: int, body: TransactionIn, uid: int = Depends(user_id),
                       repo=Depends(get_repo)):
    """Full replacement: send every field, as the Ledger edit form does."""
    return repo.update_transaction(uid, id, body.model_dump())


@router.delete("/{id}", status_code=204)
def delete_transaction(id: int, uid: int = Depends(user_id), repo=Depends(get_repo)):
    repo.delete_transaction(uid, id)
    return Response(status_code=204)
