from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.database import Base, TimestampMixin


# Usuarios que pueden iniciar sesión en la API (no confundir con Student,
# que es el recurso del CRUD).
class UserModel(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(255), unique=True)
    passwordHash: Mapped[str] = mapped_column("password_hash", String(255))


# Sesiones iniciadas. Al navegador solo llega una cookie con el `id` de la
# sesión (un valor aleatorio); el resto de los datos queda en esta tabla.
class UserSessionModel(Base):
    __tablename__ = "user_sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    # Si se elimina el usuario, se eliminan sus sesiones.
    userId: Mapped[UUID] = mapped_column(
        "user_id", ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    expiresAt: Mapped[datetime] = mapped_column(
        "expires_at", DateTime(timezone=True), index=True
    )


class PasswordResetTokenModel(Base):
    __tablename__ = "password_reset_tokens"

    # Coincide con el claim jti del JWT; su clave primaria impide duplicados.
    jti: Mapped[str] = mapped_column(String(64), primary_key=True)
    userId: Mapped[UUID] = mapped_column(
        "user_id", ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    expiresAt: Mapped[datetime] = mapped_column(
        "expires_at", DateTime(timezone=True), index=True
    )
    # NULL significa pendiente. El endpoint reset asigna la fecha de uso
    # dentro de la misma transacción que cambia la contraseña.
    usedAt: Mapped[datetime | None] = mapped_column(
        "used_at", DateTime(timezone=True), nullable=True
    )
