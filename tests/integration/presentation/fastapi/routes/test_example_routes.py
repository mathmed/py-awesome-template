from faker import Faker
from fastapi.testclient import TestClient
from pytest import fixture

from app.main.main import app


@fixture
def client() -> TestClient:
    return TestClient(app)


def test_should_insert_model_and_return_message(client: TestClient, faker: Faker) -> None:
    field1 = faker.word()
    response = client.get("/example", params={"field1": field1})
    assert response.status_code == 200
    assert response.json() == {"message": f"Model inserted! {{'field1': '{field1}'}}"}
