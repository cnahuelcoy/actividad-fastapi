"""Datos E2E de pets; reutilizan auth_client y db_session de la suite común.

Las fábricas siguen tests/students/conftest.py de la base del profesor.
Se mantienen en este directorio para no alterar fixtures de unitarias.
"""

import pytest


@pytest.fixture
def student_payload():
    def build(**overrides):
        return {
            "name": "Ana Pérez",
            "username": "ana_perez",
            "email": "ana@example.com",
            "age": 21,
        } | overrides

    return build


@pytest.fixture
def pet_payload():
    def build(**overrides):
        return {"name": "Firulais", "species": "perro", "age": 3} | overrides

    return build


@pytest.fixture
def created_student(auth_client, student_payload):
    response = auth_client.post("/api/students", json=student_payload())
    assert response.status_code == 201, response.text
    return response.json()["data"]


@pytest.fixture
def other_student(auth_client, student_payload):
    response = auth_client.post(
        "/api/students",
        json=student_payload(username="beto", email="beto@example.com"),
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


@pytest.fixture
def pets_url(created_student):
    return f"/api/students/{created_student['id']}/pets"


@pytest.fixture
def created_pet(auth_client, pets_url, pet_payload):
    response = auth_client.post(pets_url, json=pet_payload())
    assert response.status_code == 201, response.text
    return response.json()["data"]
