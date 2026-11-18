"""Dobles de prueba y datos reutilizables para los tests de Student.

Los repositorios falsos permiten probar StudentsService sin PostgreSQL.
"""

from uuid import UUID, uuid4

import pytest

from app.pets.pets_models import PetModel
from app.shared.datetimes import utc_now
from app.students.students_models import StudentModel


class FakeStudentsRepository:
    """Repositorio en memoria con la misma interfaz que StudentsRepository."""

    def __init__(self) -> None:
        self.students: list[StudentModel] = []

    def find_all(self) -> list[StudentModel]:
        return list(self.students)

    def find_by_id(self, student_id: UUID) -> StudentModel | None:
        return next(
            (student for student in self.students if student.id == student_id), None
        )

    def find_by_email(self, email: str) -> StudentModel | None:
        return next(
            (student for student in self.students if student.email == email), None
        )

    def find_by_username(self, username: str) -> StudentModel | None:
        return next(
            (student for student in self.students if student.username == username),
            None,
        )

    def add(self, student: StudentModel) -> StudentModel:
        # SQLAlchemy asigna id y timestamps en el flush. El fake los asigna
        # para que Student.model_validate pueda construir la respuesta.
        student.id = uuid4()
        now = utc_now()
        student.createdAt = now
        student.updatedAt = now
        self.students.append(student)
        return student

    def delete(self, student: StudentModel) -> None:
        self.students.remove(student)


class FakePetsRepository:
    """Repositorio en memoria con la misma interfaz que PetsRepository."""

    def __init__(self) -> None:
        self.pets: list[PetModel] = []

    def find_by_student_and_name(self, student_id: UUID, name: str) -> PetModel | None:
        return next(
            (
                pet
                for pet in self.pets
                if pet.studentId == student_id and pet.name == name
            ),
            None,
        )

    def add(self, pet: PetModel) -> PetModel:
        # Igual que con los estudiantes, el fake simula el flush de SQLAlchemy.
        pet.id = uuid4()
        now = utc_now()
        pet.createdAt = now
        pet.updatedAt = now
        self.pets.append(pet)
        return pet


@pytest.fixture
def fake_students_repository() -> FakeStudentsRepository:
    """Entrega un repositorio de estudiantes en memoria."""
    return FakeStudentsRepository()


@pytest.fixture
def fake_pets_repository() -> FakePetsRepository:
    """Entrega un repositorio de mascotas en memoria."""
    return FakePetsRepository()


@pytest.fixture
def student_payload():
    """Devuelve una fábrica de payloads válidos para crear estudiantes."""

    def build(**overrides: object) -> dict[str, object]:
        data: dict[str, object] = {
            "name": "Ana Pérez",
            "username": "ana_perez",
            "email": "ana@example.com",
            "age": 21,
        }
        data.update(overrides)
        return data

    return build


@pytest.fixture
def pet_payload():
    """Devuelve una fábrica de payloads válidos para crear mascotas."""

    def build(**overrides: object) -> dict[str, object]:
        data: dict[str, object] = {
            "name": "Firulais",
            "species": "perro",
            "age": 3,
        }
        data.update(overrides)
        return data

    return build


@pytest.fixture
def make_student_model():
    """Devuelve una fábrica de StudentModel con id y fechas asignados."""

    def build(**overrides: object) -> StudentModel:
        now = utc_now()
        values: dict[str, object] = {
            "id": uuid4(),
            "name": "Ana Pérez",
            "username": "ana_perez",
            "email": "ana@example.com",
            "age": 21,
            "createdAt": now,
            "updatedAt": now,
        }
        values.update(overrides)
        return StudentModel(**values)

    return build


@pytest.fixture
def created_student(auth_client, student_payload) -> dict[str, object]:
    """Crea un estudiante autenticado y devuelve los datos de la respuesta."""
    response = auth_client.post("/api/students", json=student_payload())
    assert response.status_code == 201, response.text
    return response.json()["data"]
