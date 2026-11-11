from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.auth.auth_schemas import LoginDto, RegisterDto, ResetPasswordDto, User
from app.auth.auth_service import AuthServiceDep
from app.auth.session import (
    UNAUTHORIZED_MESSAGE,
    CurrentSession,
    destroy_session,
    session_cookie,
    start_session,
)
from app.shared.database import DbSession
from app.users.users_repository import UsersRepository

router = APIRouter(prefix="/api/auth", tags=["Auth"])

SessionCookie = Annotated[str | None, Depends(session_cookie)]


# Crea la cuenta e inicia sesión de inmediato.
@router.post("/register", status_code=201)
def register(
    body: RegisterDto,
    response: Response,
    service: AuthServiceDep,
    db: DbSession,
    session_id: SessionCookie,
) -> User:
    user = service.register(body)
    start_session(db, response, user, session_id)
    return User.model_validate(user)


@router.post("/login")
def login(
    body: LoginDto,
    response: Response,
    service: AuthServiceDep,
    db: DbSession,
    session_id: SessionCookie,
) -> User:
    user = service.login(body)
    start_session(db, response, user, session_id)
    return User.model_validate(user)


@router.post("/logout")
def logout(response: Response, db: DbSession, session_id: SessionCookie) -> None:
    destroy_session(db, response, session_id)


@router.post(
    "/password/reset",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses={401: {"description": "Token inválido, vencido o utilizado"}},
)
def reset_password(body: ResetPasswordDto, service: AuthServiceDep) -> Response:
    service.reset_password(body)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me")
def me(session: CurrentSession, response: Response, db: DbSession) -> User:
    user = UsersRepository(db).find_by_id(session.userId)

    # La sesión apunta a un usuario que ya no existe.
    if user is None:
        destroy_session(db, response, session.id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=UNAUTHORIZED_MESSAGE
        )

    return User.model_validate(user)
