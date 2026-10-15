from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.exceptions import NotFound

from base.decorators import extend_response
from base.exceptions import SerializerError
from base.views import BaseAV
from modules.leads.api.v1.serializers import (
    DiscussionSavedSerializer,
    DiscussionSerializer,
    LeadCreateSerializer,
    LeadSerializer,
    LeadUpdateSerializer,
    with_last_note,
)
from modules.leads.models import Lead, LeadStatus

CLOSED = (LeadStatus.WON, LeadStatus.LOST)


def leads():
    return with_last_note(Lead.objects.select_related("created_by"))


def lead_or_404(pk) -> Lead:
    lead = leads().filter(pk=pk).first()
    if lead is None:
        raise NotFound("Lead not found.")
    return lead


def today_bounds():
    "Start and end of today in the app's timezone (settings.TIME_ZONE)."
    start = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
    return start, start + timedelta(days=1)


class LeadListAV(BaseAV):
    "All leads, newest first (GET); create a lead (POST)."

    # ponytail: unpaginated; add base.pagination.DefaultPagination when lists grow.
    @extend_schema(
        parameters=[
            OpenApiParameter("status", enum=LeadStatus.values, description="Only this status"),
            OpenApiParameter("q", description="Search name, company or phone"),
        ]
    )
    @extend_response(LeadSerializer(many=True))
    def get(self, request):
        qs = leads().order_by("-created_at", "-id")
        status = request.query_params.get("status")
        if status:
            if status not in LeadStatus.values:
                self.fail(f"Unknown status: {status}.")
            qs = qs.filter(lead_status=status)
        if q := request.query_params.get("q", "").strip():
            qs = qs.filter(
                Q(name__icontains=q) | Q(company__icontains=q) | Q(phone__icontains=q)
            )
        return LeadSerializer(qs, many=True).data

    @extend_schema(request=LeadCreateSerializer)
    @extend_response(LeadSerializer())
    def post(self, request):
        serializer = LeadCreateSerializer(data=request.data)
        if not serializer.is_valid():
            raise SerializerError(serializer.errors)
        lead = serializer.save(created_by=request.user)
        return LeadSerializer(lead_or_404(lead.pk)).data


class LeadDetailAV(BaseAV):
    "One lead (GET); update status or other fields (PUT, send only what changes)."

    @extend_schema(operation_id="get_api_lead")
    @extend_response(LeadSerializer())
    def get(self, request, pk):
        return LeadSerializer(lead_or_404(pk)).data

    @extend_schema(request=LeadUpdateSerializer, operation_id="put_api_lead")
    @extend_response(LeadSerializer())
    def put(self, request, pk):
        serializer = LeadUpdateSerializer(lead_or_404(pk), data=request.data, partial=True)
        if not serializer.is_valid():
            raise SerializerError(serializer.errors)
        serializer.save()
        return LeadSerializer(lead_or_404(pk)).data


class DiscussionAV(BaseAV):
    "A lead's discussions, newest first (GET); add one (POST)."

    @extend_response(DiscussionSerializer(many=True))
    def get(self, request, pk):
        lead = lead_or_404(pk)
        qs = lead.discussions.select_related("created_by")
        return DiscussionSerializer(qs, many=True).data

    @extend_schema(request=DiscussionSerializer)
    @extend_response(DiscussionSavedSerializer())
    def post(self, request, pk):
        lead = lead_or_404(pk)
        serializer = DiscussionSerializer(data=request.data)
        if not serializer.is_valid():
            raise SerializerError(serializer.errors)
        # The note and the lead's next follow-up save together or not at all.
        with transaction.atomic():
            discussion = serializer.save(lead=lead, created_by=request.user)
            if discussion.follow_up_at:
                lead.next_follow_up_at = discussion.follow_up_at
                lead.save(update_fields=["next_follow_up_at", "updated_at"])
        return {
            "discussion": DiscussionSerializer(discussion).data,
            "lead": LeadSerializer(lead_or_404(pk)).data,
        }


class FollowUpsTodayAV(BaseAV):
    "Leads with a follow-up due today (app timezone), earliest first."

    @extend_response(LeadSerializer(many=True))
    def get(self, request):
        start, end = today_bounds()
        qs = leads().filter(next_follow_up_at__gte=start, next_follow_up_at__lt=end)
        return LeadSerializer(qs.order_by("next_follow_up_at"), many=True).data


class FollowUpsOverdueAV(BaseAV):
    "Open leads whose follow-up was due before today, oldest first."

    @extend_response(LeadSerializer(many=True))
    def get(self, request):
        start, _ = today_bounds()
        qs = leads().filter(next_follow_up_at__lt=start).exclude(lead_status__in=CLOSED)
        return LeadSerializer(qs.order_by("next_follow_up_at"), many=True).data
