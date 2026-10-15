from django.db.models import OuterRef, QuerySet, Subquery
from django.utils import timezone
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from base.serializers import BaseSerializer
from modules.leads.models import Discussion, Lead, LeadStatus


def with_last_note(qs: QuerySet[Lead]) -> QuerySet[Lead]:
    "Annotate each lead with its newest discussion (the list's last-note preview)."
    newest = Discussion.objects.filter(lead=OuterRef("pk")).order_by("-created_at", "-id")
    return qs.annotate(
        last_note=Subquery(newest.values("note")[:1]),
        last_note_at=Subquery(newest.values("created_at")[:1]),
    )


class LastNoteSerializer(serializers.Serializer):
    note = serializers.CharField()
    created_at = serializers.DateTimeField()


class LeadSerializer(BaseSerializer):
    "A lead as the list and dialog show it. Read it from with_last_note()."

    status = serializers.ChoiceField(source="lead_status", choices=LeadStatus.choices)
    last_note = serializers.SerializerMethodField()
    created_by = serializers.CharField(source="created_by.name", default=None)

    class Meta:
        model = Lead
        fields = (
            "id",
            "uuid",
            "name",
            "company",
            "phone",
            "status",
            "source",
            "value",
            "next_follow_up_at",
            "last_note",
            "created_by",
            "created_at",
            "updated_at",
        )

    @extend_schema_field(LastNoteSerializer(allow_null=True))
    def get_last_note(self, obj):
        if getattr(obj, "last_note", None) is None:
            return None
        return {"note": obj.last_note, "created_at": obj.last_note_at}


class LeadCreateSerializer(BaseSerializer):
    "New leads always start as New, so status isn't accepted here."

    class Meta:
        model = Lead
        fields = ("name", "company", "phone", "source", "value")


class LeadUpdateSerializer(BaseSerializer):
    status = serializers.ChoiceField(
        source="lead_status", choices=LeadStatus.choices, required=False
    )

    class Meta:
        model = Lead
        # Clearing next_follow_up_at (null) marks the follow-up done.
        fields = ("name", "company", "phone", "status", "source", "value", "next_follow_up_at")
        # PUT sends only what changes (the view saves with partial=True).
        extra_kwargs = {"name": {"required": False}}


class DiscussionSerializer(BaseSerializer):
    created_by = serializers.CharField(source="created_by.name", default=None, read_only=True)

    class Meta:
        model = Discussion
        fields = ("id", "uuid", "note", "follow_up_at", "created_by", "created_at")
        read_only_fields = ("id", "uuid", "created_at")

    def validate_follow_up_at(self, value):
        if value is not None and value <= timezone.now():
            raise serializers.ValidationError("Pick a follow-up time in the future.")
        return value


class DiscussionSavedSerializer(serializers.Serializer):
    "The saved note plus the lead it updated."

    discussion = DiscussionSerializer()
    lead = LeadSerializer()
