from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from .auth import authenticate_user, create_token_for_user, enforce_role, get_current_user, hash_password
from .database import DatabaseSession
from .dependencies import get_db
from .models import User, UserRole
from .schemas import LoginRequest, TokenResponse, UserCreateRequest, UserRead

router = APIRouter()


@router.post("/auth/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: DatabaseSession = Depends(get_db)) -> TokenResponse:
    user = authenticate_user(db, payload.email, payload.password)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_token_for_user(db, user)
    return TokenResponse(access_token=token)


@router.post("/auth/users", response_model=UserRead, status_code=201)
def create_user(
    payload: UserCreateRequest,
    db: DatabaseSession = Depends(get_db),
) -> UserRead:
    enforce_role(db, UserRole.ADMIN)
    try:
        user = db.create_user(payload.email, hash_password(payload.password), payload.role)
    except ValueError as exc:  # pragma: no cover - guard clause
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return UserRead.model_validate(user)


@router.get("/auth/me", response_model=UserRead)
def read_current_user(current_user: User = Depends(get_current_user)) -> UserRead:
    return UserRead.model_validate(current_user)
