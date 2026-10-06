import pytest

import app as todo_app


@pytest.fixture(autouse=True)
def reset():
    todo_app.TODOS.clear()


@pytest.fixture
def client():
    todo_app.app.config["TESTING"] = True
    return todo_app.app.test_client()


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.get_json()["status"] == "ok"


def test_index_empty(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "Aucune tâche" in r.get_data(as_text=True)


def test_add_todo(client):
    client.post("/add", data={"title": "Écrire le rapport"})
    assert client.get("/api/todos").get_json()[0]["title"] == "Écrire le rapport"


def test_add_empty_title_ignored(client):
    client.post("/add", data={"title": "   "})
    assert client.get("/api/todos").get_json() == []


def test_toggle_and_delete(client):
    client.post("/add", data={"title": "Tâche"})
    todo_id = client.get("/api/todos").get_json()[0]["id"]
    client.post(f"/toggle/{todo_id}")
    assert client.get("/api/todos").get_json()[0]["done"] is True
    client.post(f"/delete/{todo_id}")
    assert client.get("/api/todos").get_json() == []


def test_html_is_escaped(client):
    client.post("/add", data={"title": "<script>alert(1)</script>"})
    assert "<script>alert(1)</script>" not in client.get("/").get_data(as_text=True)
