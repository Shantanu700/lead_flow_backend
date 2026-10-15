import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client

from modules.leads.models import Discussion, Lead

pytestmark = pytest.mark.django_db


@pytest.fixture
def debug(settings):
    settings.DEBUG = True


def test_seed_fills_every_tab(debug, django_user_model):
    call_command("seed_leads")

    assert Lead.objects.count() == 26 + 48
    assert not Lead.objects.filter(discussions=None).exists()  # every lead has notes
    user = django_user_model.objects.create_user("asha@example.com", "Lead-Flow-test-2026")
    client = Client()
    client.force_login(user)
    today = client.get("/api/follow-ups/today/").json()
    assert len(today) == 7 and sum(bool(x["follow_up_done_at"]) for x in today) == 1
    assert [x["name"] for x in client.get("/api/follow-ups/overdue/").json()] == ["Rohan Mehta", "Arjun Nair"]
    assert len(client.get("/api/follow-ups/upcoming/").json()) == 4
    reports = client.get("/api/stats/reports/?period=quarter").json()
    assert reports["win_rate"] is not None and any(b["value"] for b in reports["bars"])


def test_seed_refuses_to_double_up_and_reset_replaces(debug):
    call_command("seed_leads")
    with pytest.raises(CommandError):
        call_command("seed_leads")
    call_command("seed_leads", reset=True)
    assert Lead.objects.count() == 74
    assert Discussion.objects.count() == 74 * 2


def test_seed_is_dev_only(settings):
    settings.DEBUG = False
    with pytest.raises(CommandError):
        call_command("seed_leads")
