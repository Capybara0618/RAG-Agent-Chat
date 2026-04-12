from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import UserAccount, UserSession


class AuthRepository:
    def get_user_by_username(self, db: Session, username: str) -> UserAccount | None:
        statement = select(UserAccount).where(UserAccount.username == username)
        return db.scalar(statement)

    def get_user(self, db: Session, user_id: str) -> UserAccount | None:
        return db.get(UserAccount, user_id)

    def list_users(self, db: Session) -> list[UserAccount]:
        statement = select(UserAccount).order_by(UserAccount.role.asc(), UserAccount.username.asc())
        return list(db.scalars(statement))

    def create_user(
        self,
        db: Session,
        *,
        username: str,
        password_hash: str,
        display_name: str,
        role: str,
        department: str,
        status: str = "active",
    ) -> UserAccount:
        user = UserAccount(
            username=username,
            password_hash=password_hash,
            display_name=display_name,
            role=role,
            department=department,
            status=status,
        )
        db.add(user)
        db.flush()
        return user

    def create_session(self, db: Session, *, token: str, user_id: str) -> UserSession:
        session = UserSession(token=token, user_id=user_id)
        db.add(session)
        db.flush()
        return session

    def get_session(self, db: Session, token: str) -> UserSession | None:
        return db.get(UserSession, token)

    def delete_session(self, db: Session, token: str) -> None:
        session = db.get(UserSession, token)
        if session is None:
            return
        db.delete(session)
        db.flush()
