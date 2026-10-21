from fastapi import APIRouter, Depends, HTTPException, Request, Response

from auth import DUMMY_HASH, bearer_token, current_user, hash_password, new_session, token_hash, verify_password
from config import Config, get_config
from database import get_repo
from schemas import AuthOut, LoginIn, RegisterIn, UserOut

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=AuthOut, status_code=201)
def register(body: RegisterIn, repo=Depends(get_repo), config: Config = Depends(get_config)):
    """Create an account (with the default categories) and log straight in."""
    user = repo.create_user(body.name, body.email, hash_password(body.password))
    return {"token": new_session(repo, user["id"], config), "user": user}


@router.post("/login", response_model=AuthOut)
def login(body: LoginIn, repo=Depends(get_repo), config: Config = Depends(get_config)):
    user = repo.get_user_for_login(body.email)
    # Same message and same work whether the email or the password was wrong.
    ok = verify_password(body.password, user["password_hash"] if user else DUMMY_HASH)
    if not (user and ok):
        raise HTTPException(401, "Email or password is incorrect")
    return {"token": new_session(repo, user["id"], config), "user": user}


@router.post("/logout", status_code=204)
def logout(request: Request, repo=Depends(get_repo)):
    """Ends this session only. Succeeds even if it had already expired."""
    token = bearer_token(request)
    if token:
        repo.delete_session(token_hash(token))
    return Response(status_code=204)


@router.get("/me", response_model=UserOut)
def me(user: dict = Depends(current_user)):
    return user
