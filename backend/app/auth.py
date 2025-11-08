from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Optional

from fastapi import Depends, HTTPException
from fastapi import get_request_headers

from .config import settings
from .database import DatabaseSession
from .dependencies import get_db
from .models import User, UserRole

@dataclass
class HTTPAuthorizationCredentials:
    scheme: str
    credentials: str


class HTTPBearer:
    def __init__(self, auto_error: bool = True) -> None:
        self.auto_error = auto_error

    def __call__(self) -> HTTPAuthorizationCredentials | None:
        headers = get_request_headers()
        auth_header = headers.get("Authorization") or headers.get("authorization")
        if not auth_header:
            if self.auto_error:
                raise HTTPException(status_code=401, detail="Not authenticated")
            return None
        scheme, _, token = auth_header.partition(" ")
        if scheme.lower() != "bearer" or not token:
            if self.auto_error:
                raise HTTPException(status_code=401, detail="Invalid authentication header")
            return None
        return HTTPAuthorizationCredentials(scheme=scheme, credentials=token)


_security = HTTPBearer(auto_error=False)


def _resolve_user(db: DatabaseSession) -> User:
    credentials = _security()
    if credentials is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user = db.get_user_by_token(credentials.credentials)
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="Invalid token")
    return user


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def verify_password(password: str, password_hash: str) -> bool:
    return hash_password(password) == password_hash


def authenticate_user(db: DatabaseSession, email: str, password: str) -> Optional[User]:
    user = db.get_user_by_email(email)
    if user is None and email == settings.default_admin_email:
        user = db.create_user(
            settings.default_admin_email,
            hash_password(settings.default_admin_password),
            UserRole.ADMIN,
        )
    if user is None:
        return None
    if not user.is_active:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def create_token_for_user(db: DatabaseSession, user: User) -> str:
    return db.create_auth_token(user)


def get_current_user(db: DatabaseSession = Depends(get_db)) -> User:
    return _resolve_user(db)


def enforce_role(db: DatabaseSession, *roles: UserRole) -> User:
    user = _resolve_user(db)
    if roles and user.role not in roles:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    return user
