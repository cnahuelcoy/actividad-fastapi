from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.users.users_models import (
    PasswordResetTokenModel,
    UserModel,
    UserSessionModel,
)


class UsersRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def find_by_id(self, user_id: UUID) -> UserModel | None:
        return self.db.get(UserModel, user_id)

    def find_by_email(self, email: str) -> UserModel | None:
        return self.db.scalar(select(UserModel).where(UserModel.email == email))

    def add(self, user: UserModel) -> UserModel:
        self.db.add(user)
        self.db.flush()
        return user

    def consume_reset_token(
        self, jti: str, user_id: UUID, expires_at: datetime
    ) -> bool:
        # El UPDATE bloquea la fila y vuelve a comprobar usedAt si otra
        # transacción la modifica mientras esta petición espera.
        query = (
            update(PasswordResetTokenModel)
            .where(
                PasswordResetTokenModel.jti == jti,
                PasswordResetTokenModel.userId == user_id,
                PasswordResetTokenModel.usedAt.is_(None),
                PasswordResetTokenModel.expiresAt > func.clock_timestamp(),
                func.clock_timestamp() < expires_at,
            )
            .values(usedAt=func.clock_timestamp())
            .returning(PasswordResetTokenModel.jti)
            .execution_options(synchronize_session=False)
        )

        return self.db.scalar(query) is not None

    def update_password_hash(self, user_id: UUID, password_hash: str) -> bool:
        query = (
            update(UserModel)
            .where(UserModel.id == user_id)
            .values(passwordHash=password_hash)
            .returning(UserModel.id)
            .execution_options(synchronize_session=False)
        )

        return self.db.scalar(query) is not None

    def invalidate_sessions(self, user_id: UUID) -> None:
        self.db.execute(
            delete(UserSessionModel)
            .where(UserSessionModel.userId == user_id)
            .execution_options(synchronize_session=False)
        )
