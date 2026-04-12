from __future__ import annotations

import hashlib
import secrets

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.repositories.auth_repository import AuthRepository
from app.schemas.auth import DemoAccountRead, LoginResponse, UserProfileRead


class AuthService:
    DEMO_ACCOUNTS = (
        {
            "username": "business",
            "display_name": "业务发起部门",
            "role": "business",
            "department": "客户服务中心",
        },
        {
            "username": "manager",
            "display_name": "上级审核",
            "role": "manager",
            "department": "客户服务中心",
        },
        {
            "username": "procurement",
            "display_name": "采购部门",
            "role": "procurement",
            "department": "采购部",
        },
        {
            "username": "legal",
            "display_name": "法务部门",
            "role": "legal",
            "department": "法务部",
        },
        {
            "username": "admin",
            "display_name": "管理员",
            "role": "admin",
            "department": "平台运营中心",
        },
    )

    def __init__(self, repository: AuthRepository) -> None:
        self.repository = repository

    def seed_demo_users(self, db: Session) -> None:
        existing = {user.username for user in self.repository.list_users(db)}
        for account in self.DEMO_ACCOUNTS:
            if account["username"] in existing:
                continue
            self.repository.create_user(
                db,
                username=account["username"],
                password_hash=self.hash_password(account["username"]),
                display_name=account["display_name"],
                role=account["role"],
                department=account["department"],
            )
        db.commit()

    def list_demo_accounts(self) -> list[DemoAccountRead]:
        return [DemoAccountRead(**account) for account in self.DEMO_ACCOUNTS]

    def login(self, db: Session, *, username: str, password: str) -> LoginResponse:
        user = self.repository.get_user_by_username(db, username.strip())
        if user is None or user.status != "active" or user.password_hash != self.hash_password(password):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误。")
        token = secrets.token_hex(24)
        self.repository.create_session(db, token=token, user_id=user.id)
        db.commit()
        return LoginResponse(token=token, user=UserProfileRead.model_validate(user))

    def logout(self, db: Session, token: str) -> None:
        self.repository.delete_session(db, token)
        db.commit()

    def get_user_by_token(self, db: Session, token: str) -> UserProfileRead:
        session = self.repository.get_session(db, token)
        if session is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录已失效，请重新登录。")
        user = self.repository.get_user(db, session.user_id)
        if user is None or user.status != "active":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="当前账号不可用。")
        return UserProfileRead.model_validate(user)

    @staticmethod
    def hash_password(raw_password: str) -> str:
        return hashlib.sha256(raw_password.encode("utf-8")).hexdigest()
