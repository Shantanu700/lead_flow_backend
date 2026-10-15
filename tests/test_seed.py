from datetime import timedelta

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client
from django.utils import timezone

from modules.leads.models import Discussion, Lead

pytestmark = pytest.mark.django_db


@pytest.fixture
def debug(settings):
    settings.DEBUG = True


@pytest.fixture
def client(django_user_model):
    call_command("seed_fixtures")
    c = Client()
    c.force_login(django_user_model.objects.get(email="demo@example.com"))
    return c


def test_seed_shapes_the_pipeline_and_follow_ups(debug, client):
    by_status = client.get("/api/stats/leads/").json()["by_status"]
    open_counts = [by_status[s] for s in ("New", "Contacted", "Qualified", "Proposal Sent")]
    assert open_counts == [24, 19, 14, 10]  # narrows like a funnel
    assert by_status["Won"] > by_status["Lost"] > 0
    # Every lead has 2-5 notes.
    notes = [lead.discussions.count() for lead in Lead.objects.all()]
    assert min(notes) >= 2 and max(notes) <= 5

    today = client.get("/api/follow-ups/today/").json()
    assert len(today) == 8 and sum(bool(x["follow_up_done_at"]) for x in today) == 2
    overdue = {x["name"] for x in client.get("/api/follow-ups/overdue/").json()}
    assert overdue == {"Aisha Bello", "Rohan Mehta", "Arjun Nair", "Mateo Garcia"}
    assert len(client.get("/api/follow-ups/upcoming/").json()) >= 8


def test_seed_fills_every_report_period(debug, client):
    for period in ("week", "month", "quarter"):
        r = client.get(f"/api/stats/reports/?period={period}").json()
        assert r["deals_won"] > 0, period
        assert r["win_rate"] is not None and r["prev_win_rate"] is not None, period
    # A win on each day of this week so far.
    week = client.get("/api/stats/reports/?period=week").json()["bars"]
    assert all(b["value"] for b in week[: timezone.localtime().weekday() + 1])
    # The last six months all have revenue.
    assert all(b["value"] for b in client.get("/api/stats/reports/?period=month").json()["bars"])
    # Recent leads come from every source.
    recent = Lead.objects.filter(created_at__gte=timezone.now() - timedelta(days=30))
    assert recent.values("source").distinct().count() == 5


def test_seed_demo_login_and_guards(debug, django_user_model, monkeypatch):
    monkeypatch.setenv("DEMO_PASSWORD", "Demo-Only-Pass-2026")
    call_command("seed_fixtures")
    demo = django_user_model.objects.get(email="demo@example.com")
    assert demo.check_password("Demo-Only-Pass-2026")
    assert not Lead.objects.exclude(created_by=demo).exists()
    count = Lead.objects.count()

    with pytest.raises(CommandError):
        call_command("seed_fixtures")
    call_command("seed_fixtures", if_empty=True)  # quietly does nothing
    assert Lead.objects.count() == count

    monkeypatch.setenv("DEMO_PASSWORD", "Another-Pass-2026")
    call_command("seed_fixtures", reset=True)
    assert Lead.objects.count() == count
    assert django_user_model.objects.filter(email="demo@example.com").count() == 1
    demo.refresh_from_db()
    assert demo.check_password("Demo-Only-Pass-2026")  # existing password kept
    assert Discussion.objects.filter(lead__created_by=demo).exists()


def test_seed_needs_debug(settings):
    settings.DEBUG = False
    with pytest.raises(CommandError):
        call_command("seed_fixtures")
