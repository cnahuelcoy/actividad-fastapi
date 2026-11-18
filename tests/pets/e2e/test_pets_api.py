"""HTTP real y PostgreSQL de test, siguiendo los E2E de students.

Requiere las fixtures compartidas del profesor (client, auth_client y
db_session), con migraciones y limpieza por test. No sustituye persistencia.
"""

from datetime import datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from app.pets.pets_models import PetModel

pytestmark = pytest.mark.e2e


def envelope(response, code, message):
    assert response.status_code == code, response.text
    body = response.json()
    assert body["code"] == code
    assert body["success"] is (code < 400)
    assert body["message"] == message
    assert datetime.fromisoformat(body["timestamp"]).tzinfo is not None
    if code >= 400:
        assert body["data"] is None
    else:
        assert set(body) == {"code", "success", "message", "timestamp", "data"}
    return body


def assert_pet(data, student_id, payload):
    assert set(data) == {
        "id",
        "studentId",
        "name",
        "species",
        "age",
        "createdAt",
        "updatedAt",
    }
    assert UUID(data["id"])
    assert data["studentId"] == student_id
    for field in ("name", "species", "age"):
        assert data[field] == payload.get(field)
    for field in ("createdAt", "updatedAt"):
        assert data[field].endswith("Z")
        assert datetime.fromisoformat(data[field]).tzinfo is not None


def stored_pets(db_session):
    # Descarta la transacción/identity map de lecturas previas para observar
    # los commits de las sesiones independientes usadas por las peticiones.
    db_session.rollback()
    return {
        str(pet.id): (str(pet.studentId), pet.name, pet.species, pet.age)
        for pet in db_session.scalars(select(PetModel))
    }


@pytest.mark.parametrize("age", [None, 0, 100, "omitted"])
def test_create(auth_client, db_session, pets_url, created_student, pet_payload, age):
    payload = pet_payload(age=age)
    if age == "omitted":
        payload.pop("age")
    response = auth_client.post(pets_url, json=payload)
    data = envelope(response, 201, "Recurso creado")["data"]
    assert_pet(data, created_student["id"], payload)
    assert stored_pets(db_session) == {
        data["id"]: (created_student["id"], "Firulais", "perro", payload.get("age"))
    }


def test_list_empty(auth_client, db_session, pets_url):
    body = envelope(auth_client.get(pets_url), 200, "Operación exitosa")
    assert body["data"] == {"total": 0, "items": []}
    assert stored_pets(db_session) == {}


def test_list_only_student_pets(
    auth_client, db_session, pets_url, created_pet, other_student, pet_payload
):
    second = envelope(
        auth_client.post(pets_url, json=pet_payload(name="Michi")),
        201,
        "Recurso creado",
    )["data"]
    other = envelope(
        auth_client.post(
            f"/api/students/{other_student['id']}/pets", json=pet_payload()
        ),
        201,
        "Recurso creado",
    )["data"]
    data = envelope(auth_client.get(pets_url), 200, "Operación exitosa")["data"]
    assert set(data) == {"total", "items"}
    assert data["total"] == 2
    assert {pet["id"]: pet for pet in data["items"]} == {
        pet["id"]: pet for pet in (created_pet, second)
    }
    assert set(stored_pets(db_session)) == {
        created_pet["id"],
        second["id"],
        other["id"],
    }


def test_update(auth_client, db_session, pets_url, created_pet):
    before = stored_pets(db_session)
    response = auth_client.patch(
        f"{pets_url}/{created_pet['id']}", json={"name": "Michi", "age": 7}
    )
    data = envelope(response, 200, "Recurso actualizado")["data"]
    assert_pet(
        data, created_pet["studentId"], {**created_pet, "name": "Michi", "age": 7}
    )
    assert data["id"] == created_pet["id"]
    assert data["createdAt"] == created_pet["createdAt"]
    assert datetime.fromisoformat(data["updatedAt"]) >= datetime.fromisoformat(
        created_pet["updatedAt"]
    )
    assert stored_pets(db_session) == {
        created_pet["id"]: (before[created_pet["id"]][0], "Michi", "perro", 7)
    }
    assert auth_client.get(pets_url).json()["data"] == {"total": 1, "items": [data]}


@pytest.mark.parametrize("payload", [{}, {"name": None, "species": None, "age": None}])
def test_patch_empty_or_null_is_noop(
    auth_client, db_session, pets_url, created_pet, payload
):
    before = stored_pets(db_session)
    data = envelope(
        auth_client.patch(f"{pets_url}/{created_pet['id']}", json=payload),
        200,
        "Recurso actualizado",
    )["data"]
    assert data == created_pet
    assert stored_pets(db_session) == before


def test_delete(auth_client, db_session, pets_url, created_pet, pet_payload):
    survivor = envelope(
        auth_client.post(pets_url, json=pet_payload(name="Michi")),
        201,
        "Recurso creado",
    )["data"]
    before = stored_pets(db_session)
    response = auth_client.delete(f"{pets_url}/{created_pet['id']}")
    assert envelope(response, 200, "Recurso eliminado")["data"] == created_pet
    assert stored_pets(db_session) == {survivor["id"]: before[survivor["id"]]}
    assert auth_client.get(pets_url).json()["data"] == {"total": 1, "items": [survivor]}
    assert auth_client.delete(f"{pets_url}/{created_pet['id']}").status_code == 404


@pytest.mark.parametrize("method", ["POST", "PATCH"])
@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("name", "", "entre 1 y 50"),
        ("name", "x" * 51, "entre 1 y 50"),
        ("name", "<b>Michi</b>", "etiquetas HTML"),
        ("name", 123, "debe ser un texto"),
        ("species", "", "entre 1 y 50"),
        ("species", "x" * 51, "entre 1 y 50"),
        ("species", "<b>gato</b>", "etiquetas HTML"),
        ("species", 123, "debe ser un texto"),
        ("age", -1, "al menos 0"),
        ("age", 101, "como máximo 100"),
        ("age", 1.5, "número entero"),
        ("age", True, "número entero"),
        ("age", "3", "número entero"),
    ],
)
def test_validation(
    auth_client,
    db_session,
    pets_url,
    created_pet,
    pet_payload,
    method,
    field,
    value,
    message,
):
    before = stored_pets(db_session)
    path = pets_url if method == "POST" else f"{pets_url}/{created_pet['id']}"
    response = auth_client.request(method, path, json=pet_payload(**{field: value}))
    body = envelope(response, 400, "Error de validación")
    assert set(body["errors"]) == {field}
    assert message in body["errors"][field]["message"]
    assert stored_pets(db_session) == before


def test_missing_fields(auth_client, db_session, pets_url):
    body = envelope(auth_client.post(pets_url, json={}), 400, "Error de validación")
    assert set(body["errors"]) == {"name", "species"}
    for error in body["errors"].values():
        assert "debe ser un texto" in error["message"]
    assert stored_pets(db_session) == {}


@pytest.mark.parametrize("method", ["POST", "PATCH"])
def test_extra_field(
    auth_client, db_session, pets_url, created_pet, pet_payload, method
):
    before = stored_pets(db_session)
    path = pets_url if method == "POST" else f"{pets_url}/{created_pet['id']}"
    body = envelope(
        auth_client.request(method, path, json=pet_payload(extra="no permitido")),
        400,
        "Error de validación",
    )
    assert body["errors"] == {}
    assert stored_pets(db_session) == before


@pytest.mark.parametrize("method", ["POST", "PATCH"])
def test_duplicate_name(
    auth_client, db_session, pets_url, created_pet, pet_payload, method
):
    second = envelope(
        auth_client.post(pets_url, json=pet_payload(name="Michi")),
        201,
        "Recurso creado",
    )["data"]
    before = stored_pets(db_session)
    path = pets_url if method == "POST" else f"{pets_url}/{second['id']}"
    body = envelope(
        auth_client.request(method, path, json=pet_payload(name=created_pet["name"])),
        409,
        "Conflicto con datos existentes",
    )
    assert body["errors"] == {
        "name": {"message": "Ya tienes una mascota con ese nombre"}
    }
    assert stored_pets(db_session) == before


def test_update_own_name(auth_client, db_session, pets_url, created_pet):
    before = stored_pets(db_session)
    envelope(
        auth_client.patch(
            f"{pets_url}/{created_pet['id']}", json={"name": created_pet["name"]}
        ),
        200,
        "Recurso actualizado",
    )
    assert stored_pets(db_session) == before


@pytest.mark.parametrize("method", ["GET", "POST", "PATCH", "DELETE"])
@pytest.mark.parametrize("student_id", [str(uuid4()), "no-es-uuid"])
def test_missing_student(
    auth_client, db_session, created_pet, pet_payload, method, student_id
):
    before = stored_pets(db_session)
    path = f"/api/students/{student_id}/pets"
    if method in ("PATCH", "DELETE"):
        path += f"/{created_pet['id']}"
    body = envelope(
        auth_client.request(method, path, json=pet_payload()),
        404,
        "Estudiante no encontrado",
    )
    assert body["error"] == "Estudiante no encontrado"
    assert stored_pets(db_session) == before


@pytest.mark.parametrize("method", ["PATCH", "DELETE"])
@pytest.mark.parametrize("pet_id", [str(uuid4()), "no-es-uuid"])
def test_missing_pet(auth_client, db_session, pets_url, created_pet, method, pet_id):
    before = stored_pets(db_session)
    body = envelope(
        auth_client.request(method, f"{pets_url}/{pet_id}", json={"name": "Nuevo"}),
        404,
        "Mascota no encontrada",
    )
    assert body["error"] == "Mascota no encontrada"
    assert stored_pets(db_session) == before


@pytest.mark.parametrize("method", ["PATCH", "DELETE"])
def test_wrong_student(auth_client, db_session, created_pet, other_student, method):
    before = stored_pets(db_session)
    path = f"/api/students/{other_student['id']}/pets/{created_pet['id']}"
    body = envelope(
        auth_client.request(method, path, json={"name": "Robada"}),
        404,
        "Mascota no encontrada",
    )
    assert body["error"] == "Mascota no encontrada"
    assert stored_pets(db_session) == before


@pytest.mark.parametrize("method", ["GET", "POST", "PATCH", "DELETE"])
def test_requires_session(
    client, db_session, pets_url, created_pet, pet_payload, method
):
    before = stored_pets(db_session)
    # auth_client reutiliza client: borrar su cookie permite probar recursos reales.
    client.cookies.clear()
    path = pets_url if method in ("GET", "POST") else f"{pets_url}/{created_pet['id']}"
    body = envelope(
        client.request(method, path, json=pet_payload()),
        401,
        "Debes iniciar sesión para acceder a este recurso",
    )
    assert body["error"] == "Debes iniciar sesión para acceder a este recurso"
    assert stored_pets(db_session) == before
