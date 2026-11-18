"""Fixtures compartidas por la suite de tests.

Configuran una base PostgreSQL aislada, aplican las migraciones, limpian
las tablas antes de cada test y crean el cliente HTTP que usan los E2E.
"""

import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

ROOT = Path(__file__).resolve().parents[1]

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://postgres:postgres@localhost:5433/icinf1108_test",
)

# Debe quedar definido antes de importar cualquier módulo de la app.
os.environ["DATABASE_URL"] = TEST_DATABASE_URL


@pytest.fixture(scope="session")
def migrated_database():
    """Aplica las migraciones de Alembic a la base de test."""
    from app.shared.database import engine

    db_name = engine.url.database or ""

    # Protección para no truncar la base de desarrollo por error.
    if not db_name.endswith("_test"):
        pytest.exit(
            "La base de tests debe terminar en '_test'. "
            f"URL actual: {engine.url.render_as_string(hide_password=True)}"
        )

    config = Config(str(ROOT / "alembic.ini"))

    try:
        command.upgrade(config, "head")
    except OperationalError as error:
        pytest.exit(
            "No se pudo conectar a PostgreSQL de test. "
            "Ejecuta `make test-db` o define TEST_DATABASE_URL. "
            f"Detalle: {error}"
        )

    yield


@pytest.fixture
def clean_tables(migrated_database):
    """Vacía todas las tablas antes de cada test de base de datos."""
    import app.pets.pets_models  # noqa: F401
    import app.students.students_models  # noqa: F401
    import app.users.users_models  # noqa: F401
    from app.shared.database import Base, engine

    table_names = ", ".join(f'"{table.name}"' for table in Base.metadata.sorted_tables)

    with engine.begin() as connection:
        connection.execute(text(f"TRUNCATE {table_names} RESTART IDENTITY CASCADE"))

    yield


@pytest.fixture
def db_session(clean_tables):
    """Abre una sesión SQLAlchemy para verificar efectos en la base."""
    from app.shared.database import SessionLocal

    session = SessionLocal()

    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def client(monkeypatch, clean_tables):
    """Crea un TestClient contra la app real y la base de test."""
    from app.main import create_app

    # `StaticFiles` usa una ruta relativa a `public/`.
    monkeypatch.chdir(ROOT)

    with TestClient(create_app()) as test_client:
        yield test_client


@pytest.fixture
def auth_client(client):
    """Registra un usuario y devuelve el cliente con la cookie de sesión."""
    response = client.post(
        "/api/auth/register",
        json={
            "name": "Usuario de Prueba",
            "email": "prueba@example.com",
            "password": "password123",
        },
    )
    assert response.status_code == 201, response.text

    return client
