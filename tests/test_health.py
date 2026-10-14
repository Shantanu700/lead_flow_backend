import pytest
from django.contrib.auth import get_user_model

pytestmark = pytest.mark.django_db


def test_health_reports_ok(client):
    response = client.get("/api/health/")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_user_timestamps_and_soft_delete():
    User = get_user_model()
    user = User.objects.create_user("asha", password="not-a-real-pass-123")
    created = user.created_at

    user.name = "Asha"
    user.save()
    user.refresh_from_db()

    # created_at is fixed at insert; updated_at moves on save.
    assert user.created_at == created
    assert user.updated_at >= created

    # Soft-deleted rows disappear from objects but stay in unfiltered_objects.
    from base.enums import Status

    user.status = Status.DELETED
    user.save()
    assert not User.objects.filter(pk=user.pk).exists()
    assert User.unfiltered_objects.filter(pk=user.pk).exists()
