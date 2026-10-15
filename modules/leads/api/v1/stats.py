"""Per-tab stats. Each endpoint returns only what its tab shows, computed with
aggregate queries in the database (no lead rows are sent)."""

from datetime import datetime, timedelta

from django.db.models import (
    Avg,
    Count,
    DurationField,
    ExpressionWrapper,
    F,
    OuterRef,
    Q,
    Subquery,
    Sum,
)
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers

from base.decorators import extend_response
from base.views import BaseAV
from modules.leads.models import Discussion, Lead, LeadStatus

CLOSED = (LeadStatus.WON, LeadStatus.LOST)
OPEN = ~Q(lead_status__in=CLOSED)
WON = Q(lead_status=LeadStatus.WON)
LOST = Q(lead_status=LeadStatus.LOST)


def pct(part, whole):
    "Whole-number percentage, or None when there's nothing to divide by."
    return round(part * 100 / whole) if whole else None


def by_status():
    counts = dict(Lead.objects.values_list("lead_status").annotate(n=Count("id")))
    return {s: counts.get(s, 0) for s in LeadStatus.values}


def add_months(d: datetime, n: int) -> datetime:
    y, m = divmod(d.year * 12 + d.month - 1 + n, 12)
    return d.replace(year=y, month=m + 1, day=1)


def month_start(now: datetime) -> datetime:
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def period_ranges(period: str, now: datetime):
    """(start, end) of the current period, the previous one, and the chart
    buckets as (label, start, end). All in the app timezone."""
    day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "week":
        start = day - timedelta(days=day.weekday())  # Monday
        prev = (start - timedelta(days=7), start)
        buckets = [
            ((start + timedelta(days=i)).strftime("%a"), start + timedelta(days=i), start + timedelta(days=i + 1))
            for i in range(7)
        ]
        return (start, start + timedelta(days=7)), prev, buckets
    if period == "quarter":
        start = add_months(month_start(now), -((now.month - 1) % 3))
        prev = (add_months(start, -3), start)
        year = add_months(month_start(now), -(now.month - 1))  # 1 January
        buckets = [(f"Q{i + 1}", add_months(year, 3 * i), add_months(year, 3 * i + 3)) for i in range(4)]
        return (start, add_months(start, 3)), prev, buckets
    start = month_start(now)
    prev = (add_months(start, -1), start)
    buckets = [
        (add_months(start, i).strftime("%b"), add_months(start, i), add_months(start, i + 1))
        for i in range(-5, 1)
    ]
    return (start, add_months(start, 1)), prev, buckets


def closed_between(start, end):
    return Q(closed_at__gte=start, closed_at__lt=end)


# Response shapes (for the schema and the generated frontend client).


class StatusCountsSerializer(serializers.Serializer):
    def get_fields(self):
        return {s: serializers.IntegerField() for s in LeadStatus.values}


class DashboardStatsSerializer(serializers.Serializer):
    open_value = serializers.IntegerField()
    active_leads = serializers.IntegerField(help_text="Leads not Won or Lost")
    conversion_rate = serializers.IntegerField(allow_null=True, help_text="Won as % of all leads")
    avg_first_response_hours = serializers.FloatField(
        allow_null=True, help_text="Lead created to its first note"
    )
    won_this_month = serializers.IntegerField()
    by_status = StatusCountsSerializer()


class LeadsStatsSerializer(serializers.Serializer):
    open_value = serializers.IntegerField()
    open_leads = serializers.IntegerField()
    avg_value = serializers.IntegerField()
    win_rate = serializers.IntegerField(allow_null=True, help_text="Won as % of Won + Lost")
    by_status = StatusCountsSerializer()


class BarSerializer(serializers.Serializer):
    label = serializers.CharField()
    value = serializers.IntegerField()


class FunnelStageSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=LeadStatus.choices)
    count = serializers.IntegerField()
    value = serializers.IntegerField()


class SourceShareSerializer(serializers.Serializer):
    source = serializers.CharField(help_text='"" when not recorded')
    count = serializers.IntegerField()
    share = serializers.IntegerField(help_text="% of leads created in the period")


class ReportsStatsSerializer(serializers.Serializer):
    period = serializers.ChoiceField(choices=["week", "month", "quarter"])
    revenue = serializers.IntegerField(help_text="Value of leads won in the period")
    deals_won = serializers.IntegerField()
    avg_deal = serializers.IntegerField()
    avg_days_to_close = serializers.FloatField(allow_null=True)
    win_rate = serializers.IntegerField(allow_null=True)
    prev_win_rate = serializers.IntegerField(allow_null=True)
    bars = BarSerializer(many=True)
    funnel = FunnelStageSerializer(many=True)
    leads = serializers.IntegerField(help_text="Leads created in the period")
    sources = SourceShareSerializer(many=True)


class DashboardStatsAV(BaseAV):
    "Figures for the Dashboard tab."

    @extend_response(DashboardStatsSerializer())
    def get(self, request):
        first_note = Discussion.objects.filter(lead=OuterRef("pk")).order_by("created_at")
        totals = Lead.objects.aggregate(
            open_value=Sum("value", filter=OPEN, default=0),
            active=Count("id", filter=OPEN),
            won=Count("id", filter=WON),
            total=Count("id"),
            won_this_month=Sum(
                "value",
                filter=WON & Q(closed_at__gte=month_start(timezone.localtime())),
                default=0,
            ),
        )
        response = (
            Lead.objects.annotate(first=Subquery(first_note.values("created_at")[:1]))
            .exclude(first=None)
            .aggregate(
                avg=Avg(ExpressionWrapper(F("first") - F("created_at"), output_field=DurationField()))
            )["avg"]
        )
        return {
            "open_value": totals["open_value"],
            "active_leads": totals["active"],
            "conversion_rate": pct(totals["won"], totals["total"]),
            "avg_first_response_hours": round(response.total_seconds() / 3600, 1) if response else None,
            "won_this_month": totals["won_this_month"],
            "by_status": by_status(),
        }


class LeadsStatsAV(BaseAV):
    "Figures for the Leads tab."

    @extend_response(LeadsStatsSerializer())
    def get(self, request):
        totals = Lead.objects.aggregate(
            open_value=Sum("value", filter=OPEN, default=0),
            open_leads=Count("id", filter=OPEN),
            avg_value=Avg("value", default=0),
            won=Count("id", filter=WON),
            closed=Count("id", filter=WON | LOST),
        )
        return {
            "open_value": totals["open_value"],
            "open_leads": totals["open_leads"],
            "avg_value": round(totals["avg_value"]),
            "win_rate": pct(totals["won"], totals["closed"]),
            "by_status": by_status(),
        }


class ReportsStatsAV(BaseAV):
    "Figures for the Reports tab, for this week, month or quarter."

    @extend_schema(
        parameters=[OpenApiParameter("period", enum=["week", "month", "quarter"], default="month")]
    )
    @extend_response(ReportsStatsSerializer())
    def get(self, request):
        period = request.query_params.get("period", "month")
        if period not in ("week", "month", "quarter"):
            self.fail("Period must be week, month or quarter.")
        (start, end), (p_start, p_end), buckets = period_ranges(period, timezone.localtime())
        now, prev = closed_between(start, end), closed_between(p_start, p_end)

        totals = Lead.objects.aggregate(
            revenue=Sum("value", filter=WON & now, default=0),
            deals=Count("id", filter=WON & now),
            closed=Count("id", filter=(WON | LOST) & now),
            prev_won=Count("id", filter=WON & prev),
            prev_closed=Count("id", filter=(WON | LOST) & prev),
            to_close=Avg(
                ExpressionWrapper(F("closed_at") - F("created_at"), output_field=DurationField()),
                filter=WON & now,
            ),
            **{
                f"bar{i}": Sum("value", filter=WON & closed_between(b_start, b_end), default=0)
                for i, (_, b_start, b_end) in enumerate(buckets)
            },
        )
        stages = {
            row["lead_status"]: row
            for row in Lead.objects.values("lead_status").annotate(
                count=Count("id"), value=Sum("value", default=0)
            )
        }
        created = Lead.objects.filter(created_at__gte=start, created_at__lt=end)
        sources = created.values("source").annotate(count=Count("id")).order_by("-count", "source")
        n_created = sum(s["count"] for s in sources)

        return {
            "period": period,
            "revenue": totals["revenue"],
            "deals_won": totals["deals"],
            "avg_deal": round(totals["revenue"] / totals["deals"]) if totals["deals"] else 0,
            "avg_days_to_close": (
                round(totals["to_close"].total_seconds() / 86400, 1) if totals["to_close"] else None
            ),
            "win_rate": pct(totals["deals"], totals["closed"]),
            "prev_win_rate": pct(totals["prev_won"], totals["prev_closed"]),
            "bars": [{"label": label, "value": totals[f"bar{i}"]} for i, (label, _, _) in enumerate(buckets)],
            "funnel": [
                {
                    "status": s,
                    "count": stages.get(s, {}).get("count", 0),
                    "value": stages.get(s, {}).get("value", 0),
                }
                for s in LeadStatus.values
            ],
            "leads": n_created,
            "sources": [
                {"source": s["source"], "count": s["count"], "share": pct(s["count"], n_created)}
                for s in sources
            ],
        }
