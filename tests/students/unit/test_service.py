"""Pruebas unitarias de StudentsService.

Usan repositorios falsos para aislar la lógica de negocio. No tocan
PostgreSQL ni pasan por HTTP.
"""

from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.students.students_schemas import CreateStudentDto, UpdateStudentDto
from app.students.students_service import StudentsService

pytestmark = pytest.mark.unit


@pytest.fixture
def service(fake_students_repository, fake_pets_repository):
    """Crea StudentsService con repositorios falsos y un commit simulado."""
    db = MagicMock()
    students_service = StudentsService(db)
    students_service.repository = fake_students_repository
    students_service.pets_repository = fake_pets_repository
    return students_service


def test_find_all(service, fake_students_repository, make_student_model):
    """
    Verifica que el listado transforme los modelos al schema StudentList.

    Espera el total correcto y los estudiantes en el orden del repositorio.
    """
    fake_students_repository.students.extend(
        [
            make_student_model(name="Ana"),
            make_student_model(name="Beto", username="beto", email="beto@example.com"),
        ]
    )

    result = service.find_all()

    assert result.total == 2
    assert [student.name for student in result.items] == ["Ana", "Beto"]


def test_find_by_id(service, fake_students_repository, make_student_model):
    """Verifica que buscar por id devuelva el estudiante convertido a schema."""
    student = make_student_model()
    fake_students_repository.students.append(student)

    result = service.find_by_id(str(student.id))

    assert result.id == student.id
    assert result.email == student.email


@pytest.mark.parametrize(
    "student_id",
    [str(uuid4()), "no-es-un-uuid"],
    ids=["inexistente", "uuid-invalido"],
)
def test_find_by_id_returns_404(service, student_id):
    """Verifica que un id inexistente o inválido devuelva 404."""
    with pytest.raises(HTTPException) as error:
        service.find_by_id(student_id)

    assert error.value.status_code == 404
    assert error.value.detail == "Estudiante no encontrado"


def test_create_without_pets(service, fake_students_repository, student_payload):
    """Verifica que crear un estudiante sin mascotas lo agregue y haga commit."""
    result = service.create(CreateStudentDto(**student_payload()))

    assert result.name == "Ana Pérez"
    assert result.email == "ana@example.com"
    assert len(fake_students_repository.students) == 1
    service.db.commit.assert_called_once()


def test_create_with_pets(
    service,
    fake_students_repository,
    fake_pets_repository,
    student_payload,
    pet_payload,
):
    """
    Verifica que crear un estudiante con mascotas agregue a todos.

    Espera un solo estudiante, las mascotas del payload y un único commit.
    """
    data = student_payload(
        pets=[
            pet_payload(),
            pet_payload(name="Michi", species="gato", age=2),
        ]
    )

    result = service.create(CreateStudentDto(**data))

    assert result.name == "Ana Pérez"
    assert len(fake_students_repository.students) == 1
    assert [pet.name for pet in fake_pets_repository.pets] == [
        "Firulais",
        "Michi",
    ]
    service.db.commit.assert_called_once()


def test_create_duplicate_email(
    service,
    fake_students_repository,
    make_student_model,
    student_payload,
):
    """Verifica que un email repetido produzca 409 antes del commit."""
    fake_students_repository.students.append(make_student_model())

    with pytest.raises(HTTPException) as error:
        service.create(CreateStudentDto(**student_payload(username="otro_usuario")))

    assert error.value.status_code == 409
    assert "email" in error.value.detail["errors"]
    service.db.commit.assert_not_called()


def test_create_duplicate_username(
    service,
    fake_students_repository,
    make_student_model,
    student_payload,
):
    """Verifica que un username repetido produzca 409 antes del commit."""
    fake_students_repository.students.append(make_student_model())

    with pytest.raises(HTTPException) as error:
        service.create(CreateStudentDto(**student_payload(email="otro@example.com")))

    assert error.value.status_code == 409
    assert "username" in error.value.detail["errors"]
    service.db.commit.assert_not_called()


def test_create_duplicate_email_and_username(
    service,
    fake_students_repository,
    make_student_model,
    student_payload,
):
    """Verifica que se acumulen los errores de email y username."""
    fake_students_repository.students.append(make_student_model())

    with pytest.raises(HTTPException) as error:
        service.create(CreateStudentDto(**student_payload()))

    errors = error.value.detail["errors"]
    assert set(errors) == {"email", "username"}
    service.db.commit.assert_not_called()


def test_create_duplicate_pet_names(
    service,
    fake_pets_repository,
    student_payload,
    pet_payload,
):
    """
    Verifica que dos mascotas con el mismo nombre en el payload fallen.

    Espera 409 y que no se llame a commit.
    """
    data = student_payload(pets=[pet_payload(), pet_payload()])

    with pytest.raises(HTTPException) as error:
        service.create(CreateStudentDto(**data))

    assert error.value.status_code == 409
    assert "name" in error.value.detail["errors"]
    service.db.commit.assert_not_called()


def test_update_partial(
    service,
    fake_students_repository,
    make_student_model,
):
    """Verifica que una actualización parcial modifique solo los campos enviados."""
    student = make_student_model()
    fake_students_repository.students.append(student)

    result = service.update(
        str(student.id), UpdateStudentDto(name="Nombre Nuevo", age=30)
    )

    assert result.name == "Nombre Nuevo"
    assert result.age == 30
    assert result.email == "ana@example.com"
    assert result.username == "ana_perez"
    service.db.commit.assert_called_once()


def test_update_empty_does_not_change_fields(
    service,
    fake_students_repository,
    make_student_model,
):
    """Verifica que una actualización vacía conserve los datos y haga commit."""
    student = make_student_model()
    fake_students_repository.students.append(student)

    result = service.update(str(student.id), UpdateStudentDto())

    assert result.name == "Ana Pérez"
    assert result.email == "ana@example.com"
    service.db.commit.assert_called_once()


def test_update_conflict_with_other_email(
    service,
    fake_students_repository,
    make_student_model,
):
    """Verifica que usar el email de otro estudiante produzca 409."""
    first = make_student_model()
    second = make_student_model(name="Beto", username="beto", email="beto@example.com")
    fake_students_repository.students.extend([first, second])

    with pytest.raises(HTTPException) as error:
        service.update(str(first.id), UpdateStudentDto(email="beto@example.com"))

    assert error.value.status_code == 409
    assert "email" in error.value.detail["errors"]
    service.db.commit.assert_not_called()


def test_update_allows_same_email(
    service,
    fake_students_repository,
    make_student_model,
):
    """Verifica que el estudiante pueda conservar su propio email."""
    student = make_student_model()
    fake_students_repository.students.append(student)

    result = service.update(str(student.id), UpdateStudentDto(email="ana@example.com"))

    assert result.email == "ana@example.com"
    service.db.commit.assert_called_once()


def test_update_missing_student_returns_404(service):
    """Verifica que actualizar un id inexistente devuelva 404."""
    with pytest.raises(HTTPException) as error:
        service.update(str(uuid4()), UpdateStudentDto(name="Nombre Nuevo"))

    assert error.value.status_code == 404


def test_delete(
    service,
    fake_students_repository,
    make_student_model,
):
    """Verifica que eliminar un estudiante lo quite del repositorio y haga commit."""
    student = make_student_model()
    fake_students_repository.students.append(student)

    result = service.delete(str(student.id))

    assert result.id == student.id
    assert fake_students_repository.students == []
    service.db.commit.assert_called_once()


def test_delete_missing_student_returns_404(service):
    """Verifica que eliminar un id inexistente devuelva 404."""
    with pytest.raises(HTTPException) as error:
        service.delete(str(uuid4()))

    assert error.value.status_code == 404


def test_get_or_404_with_invalid_uuid(service):
    """Verifica que un UUID inválido se traduzca en un 404."""
    with pytest.raises(HTTPException) as error:
        service.get_or_404("no-es-un-uuid")

    assert error.value.status_code == 404
