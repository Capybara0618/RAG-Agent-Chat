from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_auth_service, get_current_user, get_db
from app.schemas.auth import DemoAccountRead, LoginRequest, LoginResponse, UserProfileRead
from app.services.auth_service import AuthService


router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/demo-accounts", response_model=list[DemoAccountRead])
def list_demo_accounts(auth_service: AuthService = Depends(get_auth_service)) -> list[DemoAccountRead]:
    return auth_service.list_demo_accounts()


@router.post("/login", response_model=LoginResponse)
def login(
    payload: LoginRequest,
    db: Session = Depends(get_db),
    auth_service: AuthService = Depends(get_auth_service),
) -> LoginResponse:
    return auth_service.login(db, username=payload.username, password=payload.password)


@router.post("/logout")
def logout(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
    auth_service: AuthService = Depends(get_auth_service),
) -> dict[str, str]:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="缺少登录凭证。")
    auth_service.logout(db, authorization.split(" ", 1)[1])
    return {"status": "ok"}


@router.get("/me", response_model=UserProfileRead)
def me(current_user: UserProfileRead = Depends(get_current_user)) -> UserProfileRead:
    return current_user
