"""Pruebas sin dependencias adicionales ni acceso a la base de datos de la app.

Ejecutar con: .venv/bin/python -B -m unittest discover -s tests -v
SQLite usa una función equivalente a clock_timestamp para estas pruebas.
La contención específica de PostgreSQL debe comprobarse también en ese motor.
"""

import asyncio
import json
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from tempfile import TemporaryDirectory
from threading import Barrier
from unittest.mock import patch
from uuid import uuid4

import jwt
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session

from app.auth.auth_schemas import ResetPasswordDto
from app.auth.auth_service import AuthService
from app.auth.password import hash_password, verify_password
from app.main import create_app
from app.shared.database import Base, get_db
from app.users.users_models import (
    PasswordResetTokenModel,
    UserModel,
    UserSessionModel,
)
from app.users.users_repository import UsersRepository

TEST_SECRET = "password-reset-test-secret-with-at-least-32-bytes"
OLD_PASSWORD = "ClaveAnterior123!"
NEW_PASSWORD = "NuevaClave456!"


async def request(app, path, body=None, *, method="POST", headers=()):
    """Invoca el ASGI real, incluido su middleware, sin servidor ni httpx."""
    messages = []
    received = False
    finished = asyncio.Event()
    encoded = json.dumps(body).encode() if body is not None else b""

    async def receive():
        nonlocal received
        if not received:
            received = True
            return {"type": "http.request", "body": encoded, "more_body": False}
        await finished.wait()
        return {"type": "http.disconnect"}

    async def send(message):
        messages.append(message)
        if message["type"] == "http.response.body" and not message.get("more_body"):
            finished.set()

    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.4"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "root_path": "",
        "query_string": b"",
        "headers": [(b"content-type", b"application/json"), *headers],
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
    }
    await asyncio.wait_for(app(scope, receive, send), timeout=15)
    start = next(m for m in messages if m["type"] == "http.response.start")
    content = b"".join(
        m.get("body", b"") for m in messages if m["type"] == "http.response.body"
    )
    return start["status"], content


class PasswordResetTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory(prefix="password-reset-", dir="/tmp")
        self.addCleanup(self.directory.cleanup)
        self.engine = create_engine(
            f"sqlite:///{self.directory.name}/tests.db",
            connect_args={"check_same_thread": False, "timeout": 10},
        )
        self.addCleanup(self.engine.dispose)

        @event.listens_for(self.engine, "connect")
        def configure_sqlite(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")
            connection.create_function(
                "clock_timestamp",
                0,
                lambda: (
                    datetime.now(UTC)
                    .replace(tzinfo=None)
                    .isoformat(sep=" ", timespec="microseconds")
                ),
            )

        Base.metadata.create_all(
            self.engine,
            tables=[
                UserModel.__table__,
                UserSessionModel.__table__,
                PasswordResetTokenModel.__table__,
            ],
        )
        self.user_id = uuid4()
        self.other_user_id = uuid4()
        self.jti = uuid4().hex
        self.expiration = datetime.now(UTC) + timedelta(minutes=10)
        self.original_hash = hash_password(OLD_PASSWORD)
        self.claims = {
            "sub": str(self.user_id),
            "jti": self.jti,
            "exp": int(self.expiration.timestamp()),
            "purpose": "password_reset",
        }

        with Session(self.engine) as db:
            db.add_all(
                [
                    UserModel(
                        id=self.user_id,
                        name="Usuario",
                        email="usuario@example.com",
                        passwordHash=self.original_hash,
                    ),
                    UserModel(
                        id=self.other_user_id,
                        name="Otro usuario",
                        email="otro@example.com",
                        passwordHash=self.original_hash,
                    ),
                ]
            )
            db.flush()
            db.add(
                PasswordResetTokenModel(
                    jti=self.jti,
                    userId=self.user_id,
                    expiresAt=self.expiration,
                )
            )
            db.add_all(
                [
                    UserSessionModel(
                        id=session_id, userId=user_id, expiresAt=self.expiration
                    )
                    for session_id, user_id in (
                        ("session-one", self.user_id),
                        ("session-two", self.user_id),
                        ("other-session", self.other_user_id),
                    )
                ]
            )
            db.commit()

        self.secret_patch = patch(
            "app.auth.auth_service.PASSWORD_RESET_JWT_SECRET", TEST_SECRET
        )
        self.secret_patch.start()
        self.addCleanup(self.secret_patch.stop)
        self.app = create_app()

        def test_db():
            with Session(self.engine, expire_on_commit=False) as db:
                yield db

        self.app.dependency_overrides[get_db] = test_db

    def token(self, **claims):
        return jwt.encode(self.claims | claims, TEST_SECRET, algorithm="HS256")

    def reset(self, token=None, password=NEW_PASSWORD):
        return asyncio.run(
            request(
                self.app,
                "/api/auth/password/reset",
                {
                    "reset_token": self.token() if token is None else token,
                    "new_password": password,
                },
            )
        )

    def assert_unchanged(self):
        with Session(self.engine) as db:
            self.assertEqual(
                db.get(UserModel, self.user_id).passwordHash, self.original_hash
            )
            self.assertIsNone(db.get(PasswordResetTokenModel, self.jti).usedAt)
            self.assertEqual(len(list(db.scalars(select(UserSessionModel)))), 3)

    def test_success_returns_empty_204_and_invalidates_only_user_sessions(self):
        self.assertEqual(self.reset(), (204, b""))

        with Session(self.engine) as db:
            stored = db.get(UserModel, self.user_id).passwordHash
            self.assertTrue(verify_password(NEW_PASSWORD, stored))
            self.assertFalse(verify_password(OLD_PASSWORD, stored))
            self.assertIsNotNone(db.get(PasswordResetTokenModel, self.jti).usedAt)
            sessions = list(db.scalars(select(UserSessionModel)))
            self.assertEqual([session.id for session in sessions], ["other-session"])

        status, _ = asyncio.run(
            request(
                self.app,
                "/api/auth/me",
                method="GET",
                headers=[(b"cookie", b"sid=session-one")],
            )
        )
        self.assertEqual(status, 401)

    def test_invalid_jwts_return_401_without_changes(self):
        invalid_tokens = [
            "",
            "token-invalido",
            jwt.encode(self.claims, TEST_SECRET + "wrong", algorithm="HS256"),
            jwt.encode(self.claims, TEST_SECRET, algorithm="HS384"),
            jwt.encode(self.claims, key=None, algorithm="none"),
            self.token(exp=int(datetime.now(UTC).timestamp()) - 10),
            self.token(purpose="login"),
            self.token(sub="usuario-invalido"),
            self.token(sub=42),
            self.token(jti=42),
            self.token(jti=""),
            self.token(jti="x" * 65),
            self.token(jti="\x00"),
            self.token(exp="invalido"),
            self.token(exp=[]),
            self.token(exp=float("inf")),
        ]
        for claim in ("sub", "jti", "exp", "purpose"):
            payload = {key: value for key, value in self.claims.items() if key != claim}
            invalid_tokens.append(jwt.encode(payload, TEST_SECRET, algorithm="HS256"))

        for index, token in enumerate(invalid_tokens):
            with self.subTest(case=index):
                status, content = self.reset(token)
                self.assertEqual(status, 401)
                self.assertEqual(json.loads(content)["code"], 401)

        self.assert_unchanged()

    def test_jti_must_belong_to_subject(self):
        self.assertEqual(self.reset(self.token(sub=str(self.other_user_id)))[0], 401)
        self.assert_unchanged()

    def test_unknown_jti_is_rejected(self):
        self.assertEqual(self.reset(self.token(jti=uuid4().hex))[0], 401)
        self.assert_unchanged()

    def test_expired_database_token_is_rejected(self):
        with Session(self.engine) as db:
            db.get(PasswordResetTokenModel, self.jti).expiresAt = datetime.now(
                UTC
            ) - timedelta(seconds=10)
            db.commit()

        self.assertEqual(self.reset()[0], 401)
        self.assert_unchanged()

    def test_used_token_is_rejected(self):
        with Session(self.engine) as db:
            db.get(PasswordResetTokenModel, self.jti).usedAt = datetime.now(UTC)
            db.commit()

        self.assertEqual(self.reset()[0], 401)
        with Session(self.engine) as db:
            self.assertEqual(
                db.get(UserModel, self.user_id).passwordHash, self.original_hash
            )
            self.assertEqual(len(list(db.scalars(select(UserSessionModel)))), 3)

    def test_reuse_does_not_change_password_again(self):
        self.assertEqual(self.reset()[0], 204)
        self.assertEqual(self.reset(password="OtraClave789!")[0], 401)
        with Session(self.engine) as db:
            self.assertTrue(
                verify_password(
                    NEW_PASSWORD, db.get(UserModel, self.user_id).passwordHash
                )
            )

    def test_failure_rolls_back_password_token_and_deleted_sessions(self):
        invalidate = UsersRepository.invalidate_sessions

        def fail_after_delete(repository, user_id):
            invalidate(repository, user_id)
            raise RuntimeError("Fallo simulado después de eliminar sesiones")

        data = ResetPasswordDto(reset_token=self.token(), new_password=NEW_PASSWORD)
        with (
            patch.object(UsersRepository, "invalidate_sessions", fail_after_delete),
            Session(self.engine) as db,
        ):
            with self.assertRaisesRegex(RuntimeError, "Fallo simulado"):
                AuthService(db).reset_password(data)
            self.assertFalse(db.in_transaction())

        self.assert_unchanged()
        self.assertEqual(self.reset()[0], 204)

    def test_concurrent_requests_only_one_succeeds(self):
        barrier = Barrier(2, timeout=10)
        consume = UsersRepository.consume_reset_token

        def consume_together(repository, jti, user_id, expires_at):
            barrier.wait()
            return consume(repository, jti, user_id, expires_at)

        passwords = [NEW_PASSWORD, "OtraClave789!"]
        with (
            patch.object(UsersRepository, "consume_reset_token", consume_together),
            ThreadPoolExecutor(max_workers=2) as executor,
        ):
            results = list(
                executor.map(lambda value: self.reset(password=value), passwords)
            )

        self.assertCountEqual([status for status, _ in results], [204, 401])
        winner = next(
            password
            for password, (status, _) in zip(passwords, results, strict=True)
            if status == 204
        )
        with Session(self.engine) as db:
            self.assertTrue(
                verify_password(winner, db.get(UserModel, self.user_id).passwordHash)
            )

    def test_invalid_password_does_not_consume_token(self):
        for password in ("corta", "x" * 73, None, 12345678):
            with self.subTest(password=password):
                self.assertEqual(self.reset(password=password)[0], 400)
        self.assert_unchanged()

    def test_login_still_returns_envelope(self):
        status, content = asyncio.run(
            request(
                self.app,
                "/api/auth/login",
                {"email": "usuario@example.com", "password": OLD_PASSWORD},
            )
        )
        self.assertEqual(status, 200)
        envelope = json.loads(content)
        self.assertTrue(envelope["success"])
        self.assertEqual(envelope["data"]["id"], str(self.user_id))


if __name__ == "__main__":
    unittest.main()
