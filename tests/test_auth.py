import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client

pytestmark = pytest.mark.django_db

PASSWORD = "Lead-Flow-test-2026"


def register(client, **overrides):
    body = {"name": "Asha Rao", "email": "asha@example.com", "password": PASSWORD} | overrides
    return client.post("/core/register/", body, content_type="application/json")


def login(client, email="asha@example.com", password=PASSWORD):
    return client.post(
        "/core/login/", {"email": email, "password": password}, content_type="application/json"
    )


def test_register_signs_in_and_returns_user(client):
    response = register(client)

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "asha@example.com"
    assert body["name"] == "Asha Rao"
    assert "password" not in body
    assert client.get("/core/login/").json()["email"] == "asha@example.com"


def test_register_rejects_duplicate_email_case_insensitively(client):
    register(client)
    response = register(Client(), email="ASHA@Example.com")

    assert response.status_code == 400
    assert "email" in response.json()


def test_register_rejects_weak_password(client):
    response = register(client, password="12345678")

    assert response.status_code == 400
    assert "password" in response.json()


def test_register_stores_email_lowercase(client):
    register(client, email="Ravi.Kumar@Example.COM")

    assert get_user_model().objects.get().email == "ravi.kumar@example.com"


def test_login_ignores_email_case_and_rejects_wrong_password(client):
    get_user_model().objects.create_user("asha@example.com", PASSWORD, name="Asha")

    assert login(Client(), password="wrong-password-1").status_code == 401
    assert login(client, email="ASHA@example.com").status_code == 201
    assert client.get("/core/login/").status_code == 200


def test_password_with_colon_works(client):
    get_user_model().objects.create_user("asha@example.com", "pass:with:colons-99", name="Asha")

    assert login(client, password="pass:with:colons-99").status_code == 201


def test_me_requires_login(client):
    response = client.get("/core/login/")

    assert response.status_code == 401
    assert "msg" in response.json()


def test_logout_clears_session(client):
    register(client)

    assert client.delete("/core/login/").status_code == 200
    assert client.get("/core/login/").status_code == 401


def test_csrf_endpoint_issues_token(client):
    response = client.get("/core/csrf/")

    assert response.status_code == 200
    assert response.json()["csrf_token"]
    assert "csrftoken" in response.cookies


def test_authenticated_write_requires_csrf_token():
    client = Client(enforce_csrf_checks=True)
    # Anonymous sign-up needs no token (DRF only enforces CSRF for sessions).
    assert register(client).status_code == 201

    assert client.delete("/core/login/").status_code == 403

    token = client.get("/core/csrf/").json()["csrf_token"]
    assert client.delete("/core/login/", HTTP_X_CSRFTOKEN=token).status_code == 200


def test_createsuperuser_with_email(monkeypatch):
    monkeypatch.setenv("DJANGO_SUPERUSER_PASSWORD", PASSWORD)
    call_command(
        "createsuperuser", interactive=False, email="Admin@Example.com", name="Admin", verbosity=0
    )

    user = get_user_model().objects.get(email="admin@example.com")
    assert user.is_superuser and user.is_staff and user.check_password(PASSWORD)
