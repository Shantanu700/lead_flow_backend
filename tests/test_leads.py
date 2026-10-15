from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.utils import timezone

from modules.leads.models import Discussion, Lead

pytestmark = pytest.mark.django_db


@pytest.fixture
def api(client):
    user = get_user_model().objects.create_user("asha@example.com", "Lead-Flow-test-2026", name="Asha Rao")
    client.force_login(user)
    return client


def post(client, url, body):
    return client.post(url, body, content_type="application/json")


def put(client, url, body):
    return client.put(url, body, content_type="application/json")


def create(client, **body):
    return post(client, "/api/leads/", {"name": "Sarah Connor"} | body).json()


def test_leads_need_sign_in():
    assert Client().get("/api/leads/").status_code == 401


def test_create_defaults_to_new_and_ignores_status(api):
    lead = create(api, company="Acme Corp", phone="555-0199", status="Won", value=18400, source="Referral")

    assert lead["status"] == "New"
    assert (lead["company"], lead["value"], lead["source"]) == ("Acme Corp", 18400, "Referral")
    assert lead["created_by"] == "Asha Rao"
    assert lead["last_note"] is None


def test_create_rejects_blank_name_and_trims(api):
    assert post(api, "/api/leads/", {"name": "   "}).status_code == 400
    assert create(api, name="  Ravi  ")["name"] == "Ravi"


def test_status_update_and_filter_keep_won_and_lost(api):
    a, b = create(api, name="A"), create(api, name="B")
    response = put(api, f"/api/leads/{a['id']}/", {"status": "Lost"})

    assert response.json()["status"] == "Lost"
    assert [x["name"] for x in api.get("/api/leads/?status=Lost").json()["results"]] == ["A"]
    assert api.get("/api/leads/").json()["count"] == 2  # Lost stays listed
    assert put(api, f"/api/leads/{b['id']}/", {"status": "Maybe"}).status_code == 400
    assert api.get("/api/leads/?status=Maybe").status_code == 400


def test_discussions_append_newest_first_and_drive_last_note(api):
    lead = create(api)
    url = f"/api/leads/{lead['id']}/discussions/"
    post(api, url, {"note": "Intro call."})
    post(api, url, {"note": "Sent pricing."})

    notes = [d["note"] for d in api.get(url).json()]
    assert notes == ["Sent pricing.", "Intro call."]
    assert api.get(f"/api/leads/{lead['id']}/").json()["last_note"]["note"] == "Sent pricing."


def test_follow_up_updates_lead_in_same_save(api):
    lead = create(api)
    when = (timezone.now() + timedelta(days=1)).replace(microsecond=0)
    body = post(api, f"/api/leads/{lead['id']}/discussions/", {"note": "Call back.", "follow_up_at": when.isoformat()}).json()

    assert body["discussion"]["follow_up_at"] == body["lead"]["next_follow_up_at"]
    assert Lead.objects.get().next_follow_up_at == when


def test_follow_up_in_the_past_saves_nothing(api):
    lead = create(api)
    past = (timezone.now() - timedelta(hours=1)).isoformat()
    response = post(api, f"/api/leads/{lead['id']}/discussions/", {"note": "Late.", "follow_up_at": past})

    assert response.status_code == 400
    assert "follow_up_at" in response.json()
    assert not Discussion.objects.exists()


def test_blank_note_rejected(api):
    lead = create(api)
    assert post(api, f"/api/leads/{lead['id']}/discussions/", {"note": "  "}).status_code == 400


def test_today_and_overdue_use_app_timezone(api, settings):
    start = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
    today = Lead.objects.create(name="Today", next_follow_up_at=start + timedelta(hours=23, minutes=30))
    Lead.objects.create(name="Tomorrow", next_follow_up_at=start + timedelta(days=1, minutes=1))
    Lead.objects.create(name="Overdue", next_follow_up_at=start - timedelta(minutes=1))
    Lead.objects.create(name="Closed", lead_status="Won", next_follow_up_at=start - timedelta(days=2))

    assert [x["name"] for x in api.get("/api/follow-ups/today/").json()] == [today.name]
    assert [x["name"] for x in api.get("/api/follow-ups/overdue/").json()] == ["Overdue"]


def test_clearing_follow_up_marks_it_done(api):
    lead = Lead.objects.create(name="X", next_follow_up_at=timezone.now() + timedelta(hours=2))
    response = put(api, f"/api/leads/{lead.pk}/", {"next_follow_up_at": None})

    assert response.json()["next_follow_up_at"] is None


def test_unknown_lead_is_404(api):
    assert api.get("/api/leads/999/").status_code == 404


def test_list_pages_on_the_server(api):
    for i in range(12):
        create(api, name=f"Lead {i:02d}", value=i * 100)

    first = api.get("/api/leads/").json()
    assert (first["count"], len(first["results"])) == (12, 10)
    assert first["next"] and first["previous"] is None
    second = api.get("/api/leads/?page=2").json()
    assert len(second["results"]) == 2
    assert len(api.get("/api/leads/?page_size=5").json()["results"]) == 5
    assert api.get("/api/leads/?page=9").status_code == 404


def test_list_orders_and_searches_notes(api):
    a, b, c = create(api, name="Bravo", value=300), create(api, name="alpha", value=100), create(api, name="Charlie", value=200)
    post(api, f"/api/leads/{a['id']}/discussions/", {"note": "Wants a pricing sheet."})

    names = lambda url: [x["name"] for x in api.get(url).json()["results"]]
    assert names("/api/leads/") == ["Bravo", "Charlie", "alpha"]  # recent: a note bumps Bravo
    assert names("/api/leads/?ordering=value") == ["Bravo", "Charlie", "alpha"]
    assert names("/api/leads/?ordering=name") == ["alpha", "Bravo", "Charlie"]
    assert names("/api/leads/?q=pricing") == ["Bravo"]
    assert api.get("/api/leads/?ordering=size").status_code == 400
