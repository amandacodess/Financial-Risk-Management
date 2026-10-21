from fastapi import APIRouter, Depends, Response

from auth import user_id
from database import get_repo
from schemas import CategoryIn, CategoryOut, TxType

router = APIRouter(prefix="/api/categories", tags=["categories"])


@router.get("", response_model=list[CategoryOut])
def list_categories(type: TxType | None = None, uid: int = Depends(user_id), repo=Depends(get_repo)):
    """Categories with how many transactions use each (a used one cannot be deleted)."""
    return repo.list_categories(uid, type)


@router.post("", response_model=CategoryOut, status_code=201)
def create_category(body: CategoryIn, uid: int = Depends(user_id), repo=Depends(get_repo)):
    return repo.create_category(uid, body.name, body.type)


@router.delete("/{id}", status_code=204)
def delete_category(id: int, uid: int = Depends(user_id), repo=Depends(get_repo)):
    repo.delete_category(uid, id)
    return Response(status_code=204)
