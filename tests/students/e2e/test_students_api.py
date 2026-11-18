"""Pruebas E2E de la API de Student.

Usan TestClient, una base PostgreSQL real y una sesión autenticada.
Cubren el recorrido completo: router, dependencias, servicio, repositorio
y envelope de respuesta.
"""

from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from app.pets.pets_models import PetModel

pytestmark = pytest.mark.e2e


def create_student(client, payload):
    """Crea un estudiante por HTTP y devuelve el contenido de `data`."""
    response = client.post("/api/students", json=payload)
    assert response.status_code == 201, response.text
    return response.json()["data"]


@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        ("GET", "/api/students", None),
        ("GET", f"/api/students/{uuid4()}", None),
        (
            "POST",
            "/api/students",
            {
                "name": "Ana Pérez",
                "username": "ana_perez",
                "email": "ana@example.com",
                "age": 21,
            },
        ),
        ("PATCH", f"/api/students/{uuid4()}", {"name": "Nombre Nuevo"}),
        ("DELETE", f"/api/students/{uuid4()}", None),
    ],
    ids=["listar", "obtener", "crear", "actualizar", "eliminar"],
)
def test_requires_session(client, method, path, payload):
    """
    Verifica que los endpoints de Student rechacen peticiones sin sesión.

    Espera 401, `success` falso y el mensaje en `error`.
    """
    response = client.request(method, path, json=payload)

    assert response.status_code == 401
    body = response.json()
    assert body["success"] is False
    assert body["data"] is None
    assert body["error"]


def test_list_empty(auth_client):
    """
    Verifica el listado cuando no hay estudiantes.

    Espera `total: 0`, `items: []` y el envelope estándar.
    """
    response = auth_client.get("/api/students")

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200
    assert body["message"] == "Operación exitosa"
    assert body["data"] == {"total": 0, "items": []}


def test_create_student(auth_client, student_payload):
    """
    Verifica el alta de un estudiante autenticado.

    Espera 201, los datos enviados y fechas serializadas en ISO 8601.
    """
    response = auth_client.post("/api/students", json=student_payload())

    assert response.status_code == 201
    body = response.json()
    assert body["code"] == 201
    assert body["success"] is True
    assert body["message"] == "Recurso creado"
    data = body["data"]
    assert data["name"] == "Ana Pérez"
    assert data["username"] == "ana_perez"
    assert data["email"] == "ana@example.com"
    assert data["age"] == 21
    assert UUID(data["id"])
    assert data["createdAt"].endswith("Z")
    assert data["updatedAt"].endswith("Z")


def test_create_student_with_pets(
    auth_client, db_session, student_payload, pet_payload
):
    """
    Verifica que el alta con mascotas anidadas las persista.

    La consulta directa a la base confirma que se crearon las dos mascotas.
    """
    data = student_payload(
        pets=[
            pet_payload(),
            pet_payload(name="Michi", species="gato", age=2),
        ]
    )

    response = auth_client.post("/api/students", json=data)

    assert response.status_code == 201
    student_id = UUID(response.json()["data"]["id"])
    pets = db_session.scalars(
        select(PetModel).where(PetModel.studentId == student_id)
    ).all()
    assert {pet.name for pet in pets} == {"Firulais", "Michi"}


def test_list_students(auth_client, student_payload):
    """
    Verifica que el listado incluya los estudiantes creados.

    Espera `total: 2` y los ids de ambos estudiantes.
    """
    first = create_student(auth_client, student_payload())
    second = create_student(
        auth_client,
        student_payload(
            name="Beto",
            username="beto",
            email="beto@example.com",
            age=25,
        ),
    )

    response = auth_client.get("/api/students")

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["total"] == 2
    assert {item["id"] for item in body["data"]["items"]} == {
        first["id"],
        second["id"],
    }


def test_get_student_by_id(auth_client, created_student):
    """Verifica que GET por id devuelva el estudiante creado."""
    response = auth_client.get(f"/api/students/{created_student['id']}")

    assert response.status_code == 200
    assert response.json()["data"]["id"] == created_student["id"]


def test_update_student(auth_client, created_student):
    """
    Verifica que PATCH actualice solo el campo enviado.

    Espera que el email se conserve y que un GET posterior refleje el cambio.
    """
    response = auth_client.patch(
        f"/api/students/{created_student['id']}",
        json={"name": "Nombre Nuevo"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["message"] == "Recurso actualizado"
    assert body["data"]["name"] == "Nombre Nuevo"
    assert body["data"]["email"] == created_student["email"]

    get_response = auth_client.get(f"/api/students/{created_student['id']}")
    assert get_response.json()["data"]["name"] == "Nombre Nuevo"


def test_delete_student(auth_client, created_student):
    """
    Verifica que DELETE devuelva el estudiante eliminado.

    Espera que un GET posterior responda 404.
    """
    response = auth_client.delete(f"/api/students/{created_student['id']}")

    assert response.status_code == 200
    body = response.json()
    assert body["message"] == "Recurso eliminado"
    assert body["data"]["id"] == created_student["id"]

    get_response = auth_client.get(f"/api/students/{created_student['id']}")
    assert get_response.status_code == 404


def test_delete_student_cascades_pets(
    auth_client, db_session, student_payload, pet_payload
):
    """
    Verifica que eliminar un estudiante elimine sus mascotas en cascada.

    Usa una consulta directa porque no hay endpoint de students que exponga
    mascotas. Espera que `pets` quede vacío después del DELETE.
    """
    created = create_student(auth_client, student_payload(pets=[pet_payload()]))
    student_id = UUID(created["id"])

    pets = db_session.scalars(
        select(PetModel).where(PetModel.studentId == student_id)
    ).all()
    assert len(pets) == 1

    response = auth_client.delete(f"/api/students/{student_id}")
    assert response.status_code == 200

    # Cierra la transacción de lectura para ver el DELETE confirmado por la API.
    db_session.rollback()
    pets = db_session.scalars(
        select(PetModel).where(PetModel.studentId == student_id)
    ).all()
    assert pets == []


def test_create_validation_errors(auth_client, student_payload):
    """
    Verifica que varios campos inválidos devuelvan 400.

    Espera errores por campo con el mensaje de la regla que falló.
    """
    response = auth_client.post(
        "/api/students",
        json=student_payload(
            name="ab",
            username="AB",
            email="no-es-email",
            age=17,
        ),
    )

    assert response.status_code == 400
    body = response.json()
    assert body["message"] == "Error de validación"
    errors = body["errors"]
    assert set(errors) == {"name", "username", "email", "age"}
    assert "entre 3 y 100" in errors["name"]["message"]
    assert "solo puede contener" in errors["username"]["message"]
    assert "no es válido" in errors["email"]["message"]
    assert "al menos 18" in errors["age"]["message"]


def test_create_missing_fields(auth_client):
    """
    Verifica que los campos faltantes devuelvan 400.

    Espera los mensajes configurados para el alta de estudiantes.
    """
    response = auth_client.post("/api/students", json={})

    assert response.status_code == 400
    errors = response.json()["errors"]
    assert set(errors) == {"name", "username", "email", "age"}
    assert "El nombre debe ser un texto" in errors["name"]["message"]
    assert "El nombre de usuario debe ser un texto" in errors["username"]["message"]
    assert "El correo electrónico no es válido" in errors["email"]["message"]
    assert "La edad debe ser un número entero" in errors["age"]["message"]


def test_create_rejects_extra_fields(auth_client, student_payload):
    """
    Verifica que un campo extra se rechace con 400.

    El handler actual omite `extra_forbidden`, por eso `errors` queda vacío.
    """
    response = auth_client.post(
        "/api/students", json=student_payload(extra="no permitido")
    )

    assert response.status_code == 400
    assert response.json()["errors"] == {}


def test_create_duplicate_email(auth_client, created_student, student_payload):
    """
    Verifica que un email ya registrado devuelva 409.

    Espera el error asociado al campo `email`.
    """
    response = auth_client.post(
        "/api/students",
        json=student_payload(username="otro_usuario", email=created_student["email"]),
    )

    assert response.status_code == 409
    body = response.json()
    assert body["message"] == "Conflicto con datos existentes"
    assert "email" in body["errors"]
    assert "ya está en uso" in body["errors"]["email"]["message"]


def test_create_duplicate_username(auth_client, created_student, student_payload):
    """
    Verifica que un username ya registrado devuelva 409.

    Espera el error asociado al campo `username`.
    """
    response = auth_client.post(
        "/api/students",
        json=student_payload(
            username=created_student["username"],
            email="otro@example.com",
        ),
    )

    assert response.status_code == 409
    body = response.json()
    assert "username" in body["errors"]
    assert "ya está en uso" in body["errors"]["username"]["message"]


def test_update_conflict(auth_client, student_payload):
    """Verifica que actualizar con el email de otro estudiante devuelva 409."""
    first = create_student(auth_client, student_payload())
    second = create_student(
        auth_client,
        student_payload(
            name="Beto",
            username="beto",
            email="beto@example.com",
            age=25,
        ),
    )

    response = auth_client.patch(
        f"/api/students/{first['id']}", json={"email": second["email"]}
    )

    assert response.status_code == 409
    assert "email" in response.json()["errors"]


@pytest.mark.parametrize(
    "method",
    ["GET", "PATCH", "DELETE"],
    ids=["get", "patch", "delete"],
)
def test_not_found(auth_client, method):
    """
    Verifica que operar sobre un UUID inexistente devuelva 404.

    Cubre GET, PATCH y DELETE con el mismo mensaje de error.
    """
    student_id = str(uuid4())
    kwargs = {"json": {"name": "Nombre Nuevo"}} if method == "PATCH" else {}

    response = auth_client.request(method, f"/api/students/{student_id}", **kwargs)

    assert response.status_code == 404
    body = response.json()
    assert body["message"] == "Estudiante no encontrado"
    assert body["error"] == "Estudiante no encontrado"


def test_invalid_uuid(auth_client):
    """Verifica que un id que no es UUID también devuelva 404."""
    response = auth_client.get("/api/students/no-es-un-uuid")

    assert response.status_code == 404
    assert response.json()["message"] == "Estudiante no encontrado"


def test_create_duplicate_pet_names_rolls_back(
    auth_client, student_payload, pet_payload
):
    """
    Verifica que un conflicto de mascotas no deje al estudiante persistido.

    El alta es transaccional: si una mascota falla, el rollback deja el
    listado vacío.
    """
    response = auth_client.post(
        "/api/students",
        json=student_payload(pets=[pet_payload(), pet_payload()]),
    )

    assert response.status_code == 409
    assert "name" in response.json()["errors"]

    list_response = auth_client.get("/api/students")
    assert list_response.json()["data"]["total"] == 0
