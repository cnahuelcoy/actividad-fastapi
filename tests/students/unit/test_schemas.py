"""Pruebas unitarias de los schemas de Student.

Validan las reglas de entrada sin base de datos ni HTTP. Son la primera
barrera para que un payload inválido no llegue al servicio.
"""

import pytest
from pydantic import ValidationError

from app.students.students_schemas import CreateStudentDto, UpdateStudentDto

pytestmark = pytest.mark.unit


def test_create_student_valid(student_payload):
    """
    Verifica que un payload válido construya el DTO con los datos esperados.

    Espera que `pets` quede vacío por defecto.
    """
    dto = CreateStudentDto(**student_payload())

    assert dto.name == "Ana Pérez"
    assert dto.username == "ana_perez"
    assert dto.email == "ana@example.com"
    assert dto.age == 21
    assert dto.pets == []


def test_create_student_with_pets(student_payload, pet_payload):
    """
    Verifica que las mascotas anidadas se validen y se conserven.

    Espera dos mascotas con sus nombres en el mismo orden del payload.
    """
    dto = CreateStudentDto(
        **student_payload(
            pets=[
                pet_payload(),
                pet_payload(name="Michi", species="gato", age=2),
            ]
        )
    )

    assert [pet.name for pet in dto.pets] == ["Firulais", "Michi"]


@pytest.mark.parametrize(
    ("name", "message"),
    [
        ("", "El nombre no puede estar vacío"),
        ("ab", "El nombre debe tener entre 3 y 100 caracteres"),
        ("a" * 101, "El nombre debe tener entre 3 y 100 caracteres"),
        ("<b>Ana</b>", "No se permiten etiquetas HTML"),
        (123, "El nombre debe ser un texto"),
        (None, "El nombre debe ser un texto"),
    ],
    ids=["vacio", "corto", "largo", "html", "no-texto", "none"],
)
def test_create_student_invalid_name(student_payload, name, message):
    """
    Verifica que los nombres inválidos se rechacen con el mensaje de su regla.

    Cubre vacío, longitud, etiquetas HTML y tipo incorrecto.
    """
    with pytest.raises(ValidationError) as error:
        CreateStudentDto(**student_payload(name=name))

    assert message in str(error.value)


@pytest.mark.parametrize(
    ("username", "message"),
    [
        ("", "El nombre de usuario no puede estar vacío"),
        ("ab", "El nombre de usuario debe tener entre 3 y 30 caracteres"),
        ("a" * 31, "El nombre de usuario debe tener entre 3 y 30 caracteres"),
        ("Ana_Perez", "solo puede contener minúsculas, números y guiones bajos"),
        ("ana-perez", "solo puede contener minúsculas, números y guiones bajos"),
        ("ana perez", "solo puede contener minúsculas, números y guiones bajos"),
        (123, "El nombre de usuario debe ser un texto"),
    ],
    ids=[
        "vacio",
        "corto",
        "largo",
        "mayusculas",
        "guion",
        "espacio",
        "no-texto",
    ],
)
def test_create_student_invalid_username(student_payload, username, message):
    """
    Verifica que los usernames inválidos se rechacen con su mensaje.

    Cubre vacío, longitud, mayúsculas, separadores y tipo incorrecto.
    """
    with pytest.raises(ValidationError) as error:
        CreateStudentDto(**student_payload(username=username))

    assert message in str(error.value)


@pytest.mark.parametrize(
    ("email", "message"),
    [
        ("no-es-email", "El correo electrónico no es válido"),
        ("", "El correo electrónico no puede estar vacío"),
    ],
    ids=["invalido", "vacio"],
)
def test_create_student_invalid_email(student_payload, email, message):
    """Verifica que los correos inválidos o vacíos se rechacen."""
    with pytest.raises(ValidationError) as error:
        CreateStudentDto(**student_payload(email=email))

    assert message in str(error.value)


@pytest.mark.parametrize(
    ("age", "message"),
    [
        (17, "La edad debe ser al menos 18"),
        (100, "La edad debe ser como máximo 99"),
        (21.5, "La edad debe ser un número entero"),
        (True, "La edad debe ser un número entero"),
        ("21", "La edad debe ser un número entero"),
    ],
    ids=["menor", "mayor", "decimal", "booleano", "texto"],
)
def test_create_student_invalid_age(student_payload, age, message):
    """Verifica que las edades fuera de rango o de tipo incorrecto se rechacen."""
    with pytest.raises(ValidationError) as error:
        CreateStudentDto(**student_payload(age=age))

    assert message in str(error.value)


def test_create_student_rejects_extra_fields(student_payload):
    """Verifica que un campo no declarado se rechace con `extra_forbidden`."""
    with pytest.raises(ValidationError) as error:
        CreateStudentDto(**student_payload(extra="no permitido"))

    assert error.value.errors()[0]["type"] == "extra_forbidden"


def test_create_student_invalid_nested_pet(student_payload, pet_payload):
    """Verifica que un nombre de mascota vacío se rechace dentro del estudiante."""
    with pytest.raises(ValidationError) as error:
        CreateStudentDto(**student_payload(pets=[pet_payload(name="")]))

    assert "El nombre no puede estar vacío" in str(error.value)


def test_create_student_nested_pet_age_out_of_range(student_payload, pet_payload):
    """Verifica que la edad de una mascota fuera de rango se rechace."""
    with pytest.raises(ValidationError) as error:
        CreateStudentDto(**student_payload(pets=[pet_payload(age=101)]))

    assert "La edad debe ser como máximo 100" in str(error.value)


def test_create_student_nested_pet_rejects_extra_fields(student_payload):
    """Verifica que una mascota con campos extra se rechace."""
    with pytest.raises(ValidationError) as error:
        CreateStudentDto(
            **student_payload(
                pets=[{"name": "Firulais", "species": "perro", "extra": "no"}]
            )
        )

    assert error.value.errors()[0]["type"] == "extra_forbidden"


def test_update_student_all_fields_optional():
    """
    Verifica que todos los campos de actualización sean opcionales.

    Espera un DTO con todos los valores en `None`.
    """
    dto = UpdateStudentDto()

    assert dto.model_dump() == {
        "name": None,
        "username": None,
        "email": None,
        "age": None,
    }


def test_update_student_partial():
    """Verifica que una actualización parcial deje el resto de campos en `None`."""
    dto = UpdateStudentDto(name="Nombre Nuevo", age=30)

    assert dto.name == "Nombre Nuevo"
    assert dto.age == 30
    assert dto.username is None
    assert dto.email is None


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("name", "ab", "El nombre debe tener entre 3 y 100 caracteres"),
        ("username", "Ana", "solo puede contener minúsculas, números y guiones bajos"),
        ("email", "no-es-email", "El correo electrónico no es válido"),
        ("age", 17, "La edad debe ser al menos 18"),
    ],
    ids=["nombre", "username", "email", "edad"],
)
def test_update_student_invalid_values(field, value, message):
    """Verifica que los valores inválidos se rechacen al actualizar."""
    with pytest.raises(ValidationError) as error:
        UpdateStudentDto(**{field: value})

    assert message in str(error.value)


@pytest.mark.parametrize(
    "field",
    ["name", "username", "email", "age"],
    ids=["nombre", "username", "email", "edad"],
)
def test_update_student_accepts_none(field):
    """Verifica que `None` sea aceptado en cada campo opcional."""
    dto = UpdateStudentDto(**{field: None})

    assert getattr(dto, field) is None


def test_update_student_rejects_extra_fields():
    """Verifica que un campo extra se rechace al actualizar."""
    with pytest.raises(ValidationError) as error:
        UpdateStudentDto(extra="no permitido")

    assert error.value.errors()[0]["type"] == "extra_forbidden"
