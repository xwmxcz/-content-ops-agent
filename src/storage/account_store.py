"""PostgreSQL account, revocable-session, and atomic authentication throttling storage."""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import case
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError

from src.api.passwords import normalize_username
from src.storage.content_store import AuthRateLimit, AuthSession, ContentStore, User


class UsernameTaken(ValueError):
    pass


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AccountStore:
    def __init__(self, store: ContentStore):
        self.store = store

    def create_user(self, username: str, password_hash: str) -> dict:
        username = normalize_username(username)
        with self.store._get_session() as session:
            user = User(id=uuid4().hex, username=username, password_hash=password_hash, is_active=True)
            session.add(user)
            try:
                session.flush()
                result = self._user_dict(user)
                session.commit()
                return result
            except IntegrityError as exc:
                session.rollback()
                if session.query(User.id).filter(User.username == username).first():
                    raise UsernameTaken("该用户名已被使用") from exc
                raise

    def get_user_by_username(self, username: str) -> dict | None:
        with self.store._get_session() as session:
            user = session.query(User).filter(User.username == username.strip().lower()).first()
            return self._user_dict(user) if user else None

    def create_session(self, user_id: str, minutes: int) -> tuple[str, int]:
        now = utcnow()
        expires_at = now + timedelta(minutes=max(minutes, 1))
        session_id = uuid4().hex
        with self.store._get_session() as session:
            session.query(AuthSession).filter(AuthSession.expires_at <= now).delete(synchronize_session=False)
            session.add(AuthSession(id=session_id, user_id=user_id, created_at=now, expires_at=expires_at))
            session.commit()
        return session_id, int(expires_at.timestamp())

    def resolve_session(self, session_id: str, user_id: str) -> dict | None:
        with self.store._get_session() as session:
            user = (
                session.query(User)
                .join(AuthSession, AuthSession.user_id == User.id)
                .filter(
                    AuthSession.id == session_id,
                    User.id == user_id,
                    AuthSession.expires_at > utcnow(),
                    User.is_active.is_(True),
                )
                .first()
            )
            return {"id": user.id, "username": user.username, "session_id": session_id} if user else None

    def revoke_session(self, session_id: str, user_id: str) -> None:
        with self.store._get_session() as session:
            session.query(AuthSession).filter(
                AuthSession.id == session_id,
                AuthSession.user_id == user_id,
            ).delete(synchronize_session=False)
            session.commit()

    def check_rate_limit(self, scope: str, client: str, *, limit: int, seconds: int) -> bool:
        key = hashlib.sha256(f"{scope}:{client}".encode()).hexdigest()
        now = utcnow()
        expired = AuthRateLimit.window_started_at <= now - timedelta(seconds=seconds)
        statement = insert(AuthRateLimit).values(key=key, window_started_at=now, attempts=1)
        statement = statement.on_conflict_do_update(
            index_elements=[AuthRateLimit.key],
            set_={
                "window_started_at": case((expired, now), else_=AuthRateLimit.window_started_at),
                "attempts": case((expired, 1), else_=AuthRateLimit.attempts + 1),
            },
        ).returning(AuthRateLimit.attempts)
        with self.store._get_session() as session:
            attempts = session.execute(statement).scalar_one()
            session.query(AuthRateLimit).filter(
                AuthRateLimit.window_started_at < now - timedelta(days=1),
            ).delete(synchronize_session=False)
            session.commit()
        return attempts <= limit

    @staticmethod
    def _user_dict(user: User) -> dict:
        return {
            "id": user.id,
            "username": user.username,
            "password_hash": user.password_hash,
            "is_active": user.is_active,
        }
