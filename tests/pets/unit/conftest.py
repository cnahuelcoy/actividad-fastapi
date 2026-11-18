"""Datos y repositorios simulados exclusivos de las unitarias de pets."""

from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.pets.pets_models import PetModel
from app.pets.pets_repository import PetsRepository
from app.pets.pets_service import PetsService
from app.shared.datetimes import utc_now
from app.students.students_models import StudentModel
from app.students.students_repository import StudentsRepository


@pytest.fixture
def student():
    now = utc_now()
    return StudentModel(
        id=uuid4(),
        name="Ana Pérez",
        username="ana_perez",
        email="ana@example.com",
        age=21,
        createdAt=now,
        updatedAt=now,
    )


@pytest.fixture
def make_pet(student):
    def build(**overrides):
        now = utc_now()
        values = {
            "id": uuid4(),
            "studentId": student.id,
            "name": "Firulais",
            "species": "perro",
            "age": 3,
            "createdAt": now,
            "updatedAt": now,
        }
        values.update(overrides)
        return PetModel(**values)

    return build


@pytest.fixture
def repository():
    mock = MagicMock(spec=PetsRepository)
    mock.find_all_by_student.return_value = []
    mock.find_by_id.return_value = None
    mock.find_by_student_and_name.return_value = None

    def add(pet):
        pet.id = uuid4()
        pet.createdAt = pet.updatedAt = utc_now()
        return pet

    mock.add.side_effect = add
    return mock


@pytest.fixture
def students_repository(student):
    mock = MagicMock(spec=StudentsRepository)
    mock.find_by_id.return_value = student
    return mock


@pytest.fixture
def service(repository, students_repository):
    # El servicio real usa su lógica habitual, pero ningún repositorio llega a SQL.
    instance = PetsService(MagicMock(spec=Session))
    instance.repository = repository
    instance.students_service.repository = students_repository
    return instance
