from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, status
from jwt.exceptions import InvalidTokenError

from app.auth.auth_schemas import LoginDto, RegisterDto, ResetPasswordDto
from app.auth.password import hash_password, verify_password
from app.shared.config import PASSWORD_RESET_JWT_SECRET
from app.shared.database import DbSession
from app.shared.exceptions import conflict
from app.users.users_models import UserModel
from app.users.users_repository import UsersRepository


def _invalid_reset_token() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token de recuperación inválido, vencido o utilizado",
    )


def _decode_reset_token(token: str) -> tuple[UUID, str, datetime]:
    if not PASSWORD_RESET_JWT_SECRET:
        raise RuntimeError("Falta configurar PASSWORD_RESET_JWT_SECRET")

    try:
        payload = jwt.decode(
            token,
            PASSWORD_RESET_JWT_SECRET,
            algorithms=["HS256"],
            options={
                "verify_signature": True,
                "verify_exp": True,
                "require": ["sub", "exp", "purpose", "jti"],
            },
        )

        if payload["purpose"] != "password_reset":
            raise InvalidTokenError()

        subject = payload["sub"]
        jti = payload["jti"]
        expiration = payload["exp"]

        if not isinstance(subject, str):
            raise InvalidTokenError()
        if not isinstance(jti, str) or not 1 <= len(jti) <= 64 or "\x00" in jti:
            raise InvalidTokenError()
        if type(expiration) not in (int, float):
            raise InvalidTokenError()

        return UUID(subject), jti, datetime.fromtimestamp(expiration, UTC)
    except (
        InvalidTokenError,
        KeyError,
        TypeError,
        ValueError,
        OverflowError,
        OSError,
    ):
        raise _invalid_reset_token() from None


class AuthService:
    def __init__(self, db: DbSession) -> None:
        self.db = db
        self.users_repository = UsersRepository(db)

    def register(self, data: RegisterDto) -> UserModel:
        if self.users_repository.find_by_email(data.email) is not None:
            raise conflict(
                {"email": {"message": "El correo electrónico ya está registrado"}}
            )

        user = self.users_repository.add(
            UserModel(
                name=data.name,
                email=data.email,
                passwordHash=hash_password(data.password),
            )
        )
        self.db.commit()

        return user

    def login(self, data: LoginDto) -> UserModel:
        user = self.users_repository.find_by_email(data.email)

        # Mismo mensaje si el correo no existe o la contraseña es incorrecta,
        # para no revelar qué correos están registrados.
        if user is None or not verify_password(data.password, user.passwordHash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Correo o contraseña incorrectos",
            )

        return user

    def reset_password(self, data: ResetPasswordDto) -> None:
        user_id, jti, expires_at = _decode_reset_token(data.reset_token)
        password_hash = hash_password(data.new_password)

        # El commit ocurre solo si las tres escrituras terminan correctamente.
        # Una excepción también revierte el consumo del token.
        with self.db.begin():
            if not self.users_repository.consume_reset_token(jti, user_id, expires_at):
                raise _invalid_reset_token()

            if not self.users_repository.update_password_hash(user_id, password_hash):
                raise _invalid_reset_token()

            self.users_repository.invalidate_sessions(user_id)


AuthServiceDep = Annotated[AuthService, Depends()]
