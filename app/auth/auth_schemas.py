from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, field_validator

from app.shared.datetimes import ApiDatetime
from app.shared.validation import validate_email, validate_text
from app.students.students_schemas import (
    EMAIL_MESSAGES,
    NO_HTML_PATTERN,
    STUDENT_NAME_MESSAGES,
)

PASSWORD_TYPE_MESSAGE = "La contraseña debe ser un texto"
PASSWORD_LENGTH_MESSAGE = "La contraseña debe tener entre 8 y 72 caracteres"
PASSWORD_EMPTY_MESSAGE = "La contraseña no puede estar vacía"


# Usuario sin el hash de la contraseña: lo único que sale de la API.
class User(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    email: str
    createdAt: ApiDatetime
    updatedAt: ApiDatetime


class RegisterDto(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    email: EmailStr
    password: str

    @field_validator("name", mode="before")
    @classmethod
    def _validate_name(cls, v: object) -> object:
        _raise_validation(
            validate_text(
                v,
                type_message=STUDENT_NAME_MESSAGES["type"],
                empty_message=STUDENT_NAME_MESSAGES["empty"],
                length_message=STUDENT_NAME_MESSAGES["length"],
                pattern_message=STUDENT_NAME_MESSAGES["pattern"],
                min_length=3,
                max_length=100,
                pattern=NO_HTML_PATTERN,
                check_empty=True,
                allow_none=False,
            )
        )
        return v

    @field_validator("email", mode="before")
    @classmethod
    def _validate_email(cls, v: object) -> object:
        _raise_validation(_email_errors(v))
        return v

    @field_validator("password", mode="before")
    @classmethod
    def _validate_password(cls, v: object) -> object:
        errors: list[str] = []

        if not isinstance(v, str):
            errors.append(PASSWORD_TYPE_MESSAGE)
        if not (isinstance(v, str) and 8 <= len(v) <= 72):
            errors.append(PASSWORD_LENGTH_MESSAGE)

        _raise_validation(errors)
        return v


class LoginDto(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str

    @field_validator("email", mode="before")
    @classmethod
    def _validate_email(cls, v: object) -> object:
        _raise_validation(_email_errors(v))
        return v

    @field_validator("password", mode="before")
    @classmethod
    def _validate_password(cls, v: object) -> object:
        errors: list[str] = []

        if not isinstance(v, str):
            errors.append(PASSWORD_TYPE_MESSAGE)
        if v is None or v == "":
            errors.append(PASSWORD_EMPTY_MESSAGE)

        _raise_validation(errors)
        return v


def _email_errors(v: object) -> list[str]:
    return validate_email(
        v,
        invalid_message=EMAIL_MESSAGES["invalid"],
        empty_message=EMAIL_MESSAGES["empty"],
        check_empty=True,
        allow_none=False,
    )


def _raise_validation(messages: list[str]) -> None:
    if messages:
        raise ValueError(", ".join(messages))


class ForgotPasswordDto(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr

    @field_validator("email", mode="before")
    @classmethod
    def _validate_email(cls, value: object) -> object:
        _raise_validation(_email_errors(value))
        return value


class ForgotPasswordResponse(BaseModel):
    message: str
    reset_link: str | None = None


class ResetPasswordDto(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reset_token: str
    new_password: str

    @field_validator("new_password", mode="before")
    @classmethod
    def _validate_new_password(cls, value: object) -> object:
        errors: list[str] = []

        if not isinstance(value, str):
            errors.append(PASSWORD_TYPE_MESSAGE)
        if not (isinstance(value, str) and 8 <= len(value) <= 72):
            errors.append(PASSWORD_LENGTH_MESSAGE)

        _raise_validation(errors)
        return value
