from datetime import datetime, timedelta

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from modules.leads.api.v1.stats import add_months, period_ranges
from modules.leads.models import Discussion, Lead

pytestmark = pytest.mark.django_db


@pytest.fixture
def api(client):
    user = get_user_model().objects.create_user("asha@example.com", "Lead-Flow-test-2026", name="Asha")
    client.force_login(user)
    return client


def put(client, lead, body):
    return client.put(f"/api/leads/{lead.pk}/", body, content_type="application/json").json()


def lead(**fields):
    return Lead.objects.create(**({"name": "L"} | fields))


def test_add_months_rolls_over_years():
    jan = datetime(2026, 1, 31, 9, 0)
    assert add_months(jan, -1) == datetime(2025, 12, 1, 9, 0)
    assert add_months(jan, 13) == datetime(2027, 2, 1, 9, 0)


def test_period_ranges_cover_the_current_period():
    now = timezone.localtime().replace(year=2026, month=10, day=15, hour=16)  # a Thursday
    (start, end), (p_start, _), bars = period_ranges("week", now)
    assert (start.day, end.day, p_start.day) == (12, 19, 5)
    assert [b[0] for b in bars][:2] == ["Mon", "Tue"]
    (start, end), _, bars = period_ranges("quarter", now)
    assert (start.month, end.month, [b[0] for b in bars]) == (10, 1, ["Q1", "Q2", "Q3", "Q4"])
    (start, _), _, bars = period_ranges("month", now)
    assert start.month == 10 and [b[0] for b in bars][-1] == "Oct" and len(bars) == 6


def test_closing_stamps_closed_at_and_reopening_clears_it(api):
    x = lead()
    assert put(api, x, {"status": "Won"})["closed_at"] is not None
    assert put(api, x, {"status": "Qualified"})["closed_at"] is None


def test_follow_up_done_leaves_overdue_and_new_follow_up_reopens(api):
    x = lead(next_follow_up_at=timezone.now() - timedelta(days=2))
    assert len(api.get("/api/follow-ups/overdue/").json()) == 1

    assert put(api, x, {"follow_up_done": True})["follow_up_done_at"] is not None
    assert api.get("/api/follow-ups/overdue/").json() == []

    later = (timezone.now() + timedelta(days=2)).isoformat()
    api.post(f"/api/leads/{x.pk}/discussions/", {"note": "Again.", "follow_up_at": later}, content_type="application/json")
    assert Lead.objects.get().follow_up_done_at is None


def test_upcoming_is_the_next_seven_days(api):
    start = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
    lead(name="Today", next_follow_up_at=start + timedelta(hours=20))
    lead(name="In 3 days", next_follow_up_at=start + timedelta(days=3))
    lead(name="In 9 days", next_follow_up_at=start + timedelta(days=9))

    assert [x["name"] for x in api.get("/api/follow-ups/upcoming/").json()] == ["In 3 days"]


def test_dashboard_stats(api):
    a = lead(value=1000)
    lead(value=500, lead_status="Won", closed_at=timezone.now())
    lead(value=200, lead_status="Lost", closed_at=timezone.now())
    lead(value=300)
    note = Discussion.objects.create(lead=a, note="Hi")
    Discussion.objects.filter(pk=note.pk).update(created_at=a.created_at + timedelta(hours=3))

    body = api.get("/api/stats/dashboard/").json()
    assert (body["open_value"], body["active_leads"], body["conversion_rate"]) == (1300, 2, 25)
    assert body["avg_first_response_hours"] == 3.0
    assert body["won_this_month"] == 500
    assert body["by_status"]["New"] == 2 and body["by_status"]["Proposal Sent"] == 0


def test_leads_stats(api):
    lead(value=100)
    lead(value=300, lead_status="Won")
    lead(value=200, lead_status="Lost")
    lead(value=400, lead_status="Won")

    body = api.get("/api/stats/leads/").json()
    assert body == body | {"open_value": 100, "open_leads": 1, "avg_value": 250, "win_rate": 67}


def test_reports_stats_for_the_month(api):
    now = timezone.now()
    lead(value=1000, lead_status="Won", closed_at=now, source="Referral")
    lead(value=500, lead_status="Lost", closed_at=now, source="Referral")
    lead(value=2000, lead_status="Won", closed_at=add_months(timezone.localtime(), -1), source="LinkedIn")

    body = api.get("/api/stats/reports/?period=month").json()
    assert (body["revenue"], body["deals_won"], body["avg_deal"], body["win_rate"]) == (1000, 1, 1000, 50)
    assert body["prev_win_rate"] == 100
    assert body["bars"][-1] == {"label": timezone.localtime().strftime("%b"), "value": 1000}
    assert body["bars"][-2]["value"] == 2000
    assert body["funnel"][4] == {"status": "Won", "count": 2, "value": 3000}
    assert body["leads"] == 3
    assert body["sources"][0] == {"source": "Referral", "count": 2, "share": 67}


def test_reports_rejects_unknown_period(api):
    assert api.get("/api/stats/reports/?period=year").status_code == 409


def test_stats_need_sign_in(client):
    for url in ("/api/stats/dashboard/", "/api/stats/leads/", "/api/stats/reports/"):
        assert client.get(url).status_code == 401
