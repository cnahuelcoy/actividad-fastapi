from typing import Annotated

from fastapi import Depends, HTTPException, status

from app.auth.auth_schemas import (
    ForgotPasswordDto,
    ForgotPasswordResponse,
    LoginDto,
    RegisterDto,
)
from app.auth.password import hash_password, verify_password
from app.auth.reset_token import create_reset_token
from app.shared.config import FRONTEND_URL
from app.shared.database import DbSession
from app.shared.exceptions import conflict
from app.users.users_models import UserModel
from app.users.users_repository import UsersRepository


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

        if user is None or not verify_password(data.password, user.passwordHash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Correo o contraseña incorrectos",
            )

        return user

    def forgot_password(self, data: ForgotPasswordDto) -> ForgotPasswordResponse:
        message = "Si el correo está registrado, recibirás un enlace de recuperación."
        user = self.users_repository.find_by_email(data.email)

        if user is None:
            return ForgotPasswordResponse(message=message)

        token, jti, expires_at = create_reset_token(user.id)

        return ForgotPasswordResponse(
            message=message,
            reset_link=f"{FRONTEND_URL}/reset-password?token={token}",
        )


AuthServiceDep = Annotated[AuthService, Depends()]