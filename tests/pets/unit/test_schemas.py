"""Validación de los DTO de pets sin HTTP ni base de datos."""

import pytest
from pydantic import ValidationError

from app.pets.pets_schemas import CreatePetDto, UpdatePetDto

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("age", [None, 0, 100])
def test_create_valid(age):
    dto = CreatePetDto(name="Firulais", species="perro", age=age)
    assert dto.model_dump() == {"name": "Firulais", "species": "perro", "age": age}


def test_create_optional_age():
    assert CreatePetDto(name="Michi", species="gato").age is None


@pytest.mark.parametrize("schema", [CreatePetDto, UpdatePetDto])
@pytest.mark.parametrize("field", ["name", "species"])
@pytest.mark.parametrize("value", ["", "x" * 51, "<b>Michi</b>", 123])
def test_invalid_text(schema, field, value):
    data = {"name": "Michi", "species": "gato", field: value}
    with pytest.raises(ValidationError) as error:
        schema(**data)
    assert any(item["loc"] == (field,) for item in error.value.errors())


@pytest.mark.parametrize("schema", [CreatePetDto, UpdatePetDto])
@pytest.mark.parametrize("length", [1, 50])
def test_text_length_boundaries(schema, length):
    dto = schema(name="x" * length, species="y" * length)
    assert len(dto.name) == length
    assert len(dto.species) == length


@pytest.mark.parametrize("schema", [CreatePetDto, UpdatePetDto])
@pytest.mark.parametrize("value", [-1, 101, 2.5, True, "3"])
def test_invalid_age(schema, value):
    with pytest.raises(ValidationError) as error:
        schema(name="Michi", species="gato", age=value)
    assert any(item["loc"] == ("age",) for item in error.value.errors())


@pytest.mark.parametrize("field", ["name", "species"])
@pytest.mark.parametrize("missing", [False, True], ids=["none", "ausente"])
def test_create_requires_text(field, missing):
    data = {"name": "Michi", "species": "gato"}
    if missing:
        del data[field]
    else:
        data[field] = None
    with pytest.raises(ValidationError) as error:
        CreatePetDto(**data)
    assert any(item["loc"] == (field,) for item in error.value.errors())


def test_update_all_fields_optional():
    assert UpdatePetDto().model_dump() == {"name": None, "species": None, "age": None}


@pytest.mark.parametrize("field", ["name", "species", "age"])
def test_update_accepts_none(field):
    assert getattr(UpdatePetDto(**{field: None}), field) is None


@pytest.mark.parametrize("schema", [CreatePetDto, UpdatePetDto])
def test_rejects_extra_fields(schema):
    with pytest.raises(ValidationError) as error:
        schema(name="Michi", species="gato", extra="no permitido")
    assert any(item["type"] == "extra_forbidden" for item in error.value.errors())
