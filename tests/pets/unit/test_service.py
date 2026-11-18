"""Lógica de PetsService aislada de HTTP y de la base de datos."""

from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.pets.pets_schemas import CreatePetDto, Pet, UpdatePetDto

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("count", [0, 2], ids=["vacio", "con-mascotas"])
def test_list_for_student(service, repository, student, make_pet, count):
    pets = [make_pet(name=f"Mascota {i}") for i in range(count)]
    repository.find_all_by_student.return_value = pets

    result = service.find_all_for_student(str(student.id))

    assert result.total == count
    assert [pet.id for pet in result.items] == [pet.id for pet in pets]
    repository.find_all_by_student.assert_called_once_with(student.id)
    service.db.commit.assert_not_called()


@pytest.mark.parametrize("age", [None, 0, 100])
def test_create(service, repository, student, age):
    data = CreatePetDto(name="Firulais", species="perro", age=age)

    result = service.create(str(student.id), data)

    assert isinstance(result, Pet)
    assert result.studentId == student.id
    assert result.name == "Firulais"
    assert result.species == "perro"
    assert result.age == age
    assert result.id is not None
    assert result.createdAt is not None
    repository.add.assert_called_once()
    repository.find_by_student_and_name.assert_called_once_with(student.id, "Firulais")
    service.db.commit.assert_called_once()


def test_create_duplicate_name(service, repository, student, make_pet):
    repository.find_by_student_and_name.return_value = make_pet()

    with pytest.raises(HTTPException) as error:
        service.create(str(student.id), CreatePetDto(name="Firulais", species="gato"))

    assert error.value.status_code == 409
    assert error.value.detail["errors"]["name"]["message"]
    repository.add.assert_not_called()
    service.db.commit.assert_not_called()


@pytest.mark.parametrize(
    "changes",
    [{"name": "Michi"}, {"species": "gato"}, {"age": 0}, {}, {"age": None}],
    ids=["nombre", "especie", "edad-cero", "vacio", "none-no-modifica"],
)
def test_update_partial(service, repository, student, make_pet, changes):
    pet = make_pet()
    repository.find_by_id.return_value = pet
    expected = {"name": pet.name, "species": pet.species, "age": pet.age}
    expected.update({key: value for key, value in changes.items() if value is not None})

    result = service.update(str(student.id), str(pet.id), UpdatePetDto(**changes))

    assert result.id == pet.id
    assert result.studentId == student.id
    assert result.model_dump(include={"name", "species", "age"}) == expected
    service.db.commit.assert_called_once()


def test_update_allows_own_name(service, repository, student, make_pet):
    pet = make_pet()
    repository.find_by_id.return_value = pet
    repository.find_by_student_and_name.return_value = pet

    result = service.update(str(student.id), str(pet.id), UpdatePetDto(name=pet.name))

    assert result.name == pet.name
    service.db.commit.assert_called_once()


def test_update_duplicate_name_leaves_pet_unchanged(
    service, repository, student, make_pet
):
    pet = make_pet()
    repository.find_by_id.return_value = pet
    repository.find_by_student_and_name.return_value = make_pet(name="Michi")

    with pytest.raises(HTTPException) as error:
        service.update(str(student.id), str(pet.id), UpdatePetDto(name="Michi", age=5))

    assert error.value.status_code == 409
    assert "name" in error.value.detail["errors"]
    assert pet.name == "Firulais"
    assert pet.age == 3
    service.db.commit.assert_not_called()


def test_delete(service, repository, student, make_pet):
    pet = make_pet()
    repository.find_by_id.return_value = pet

    result = service.delete(str(student.id), str(pet.id))

    assert result.id == pet.id
    assert result.name == pet.name
    repository.delete.assert_called_once_with(pet)
    service.db.commit.assert_called_once()


@pytest.mark.parametrize("operation", ["list", "create", "update", "delete"])
@pytest.mark.parametrize("student_id", ["no-es-un-uuid", str(uuid4())])
def test_missing_student(
    service, repository, students_repository, operation, student_id
):
    students_repository.find_by_id.return_value = None
    with pytest.raises(HTTPException) as error:
        if operation == "list":
            service.find_all_for_student(student_id)
        elif operation == "create":
            service.create(student_id, CreatePetDto(name="Michi", species="gato"))
        elif operation == "update":
            service.update(student_id, str(uuid4()), UpdatePetDto(name="Michi"))
        else:
            service.delete(student_id, str(uuid4()))

    assert error.value.status_code == 404
    assert error.value.detail == "Estudiante no encontrado"
    assert repository.mock_calls == []
    service.db.commit.assert_not_called()


@pytest.mark.parametrize("operation", ["update", "delete", "find_owned"])
@pytest.mark.parametrize("case", ["inexistente", "uuid-invalido", "otro-estudiante"])
def test_missing_or_foreign_pet(
    service, repository, student, make_pet, operation, case
):
    pet_id = "no-es-un-uuid" if case == "uuid-invalido" else str(uuid4())
    if case == "otro-estudiante":
        repository.find_by_id.return_value = make_pet(studentId=uuid4())

    with pytest.raises(HTTPException) as error:
        if operation == "update":
            service.update(str(student.id), pet_id, UpdatePetDto(name="Michi"))
        elif operation == "delete":
            service.delete(str(student.id), pet_id)
        else:
            service.find_owned(str(student.id), pet_id)

    assert error.value.status_code == 404
    assert error.value.detail == "Mascota no encontrada"
    repository.delete.assert_not_called()
    repository.find_by_student_and_name.assert_not_called()
    service.db.commit.assert_not_called()
    if case == "uuid-invalido":
        repository.find_by_id.assert_not_called()
