import os
from typing import Final

from dotenv import load_dotenv

# Si existe un archivo `.env`, se cargan sus variables (útil al correr la API
# sin Docker). Las variables ya definidas en el entorno tienen prioridad.
load_dotenv()


def _database_url() -> str:
    url = os.getenv(
        "DATABASE_URL", "postgres://postgres:postgres@localhost:5432/icinf1108"
    )

    # Se acepta el mismo formato que en las otras ramas (postgres://...).
    # SQLAlchemy necesita que se indique el driver: postgresql+psycopg://...
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url.removeprefix(prefix)

    return url


# Configuración leída desde variables de entorno. Los valores por defecto
# sirven para desarrollo local con el Postgres de docker-compose.yml.
DATABASE_URL: Final[str] = _database_url()

SESSION_COOKIE_NAME: Final[str] = "sid"

# Duración de la sesión (por defecto 8 horas).
SESSION_MAX_AGE_SECONDS: Final[int] = (
    int(os.getenv("SESSION_MAX_AGE_MS", str(1000 * 60 * 60 * 8))) // 1000
)

# Solo debe ser `true` cuando la app se sirve por HTTPS.
SESSION_COOKIE_SECURE: Final[bool] = os.getenv("SESSION_COOKIE_SECURE") == "true"

RESET_TOKEN_SECRET: Final[str] = os.getenv(
    "RESET_TOKEN_SECRET", "dev-reset-secret-cambiar-en-produccion"
)

RESET_TOKEN_EXPIRE_MINUTES: Final[int] = 15

FRONTEND_URL: Final[str] = os.getenv("FRONTEND_URL", "http://localhost:3000")
