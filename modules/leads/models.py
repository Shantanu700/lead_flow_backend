from django.conf import settings
from django.db import models

from base.defaults import DEFAULT_ON_DELETE
from base.model import ModelBase


class LeadStatus(models.TextChoices):
    NEW = "New"
    CONTACTED = "Contacted"
    QUALIFIED = "Qualified"
    PROPOSAL_SENT = "Proposal Sent"
    WON = "Won"
    LOST = "Lost"


class LeadSource(models.TextChoices):
    WEBSITE = "Website form"
    REFERRAL = "Referral"
    LINKEDIN = "LinkedIn"
    COLD_EMAIL = "Cold email"
    EVENTS = "Events"
    OTHER = "Other"


class Lead(ModelBase):
    """A sales lead, shared by the whole team.

    ModelBase.status is the soft-delete flag, so the pipeline stage lives in
    `lead_status`; the API exposes it as `status`.
    """

    name = models.CharField(max_length=255)
    company = models.CharField(max_length=255, blank=True)
    phone = models.CharField(max_length=32, blank=True)
    lead_status = models.CharField(
        max_length=20, choices=LeadStatus.choices, default=LeadStatus.NEW, db_index=True
    )
    source = models.CharField(max_length=20, choices=LeadSource.choices, blank=True)
    # Estimated deal value in whole rupees.
    value = models.PositiveBigIntegerField(default=0)
    # The current next follow-up; set from the discussion that scheduled it.
    next_follow_up_at = models.DateTimeField(null=True, blank=True, db_index=True)
    # When that follow-up was ticked off; cleared when a new one is scheduled.
    follow_up_done_at = models.DateTimeField(null=True, blank=True)
    # When the lead became Won or Lost; cleared if it's reopened.
    closed_at = models.DateTimeField(null=True, blank=True, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, DEFAULT_ON_DELETE, null=True, related_name="+"
    )

    def __str__(self):
        return self.name


class Discussion(ModelBase):
    "An append-only note on a lead, optionally scheduling its next follow-up."

    lead = models.ForeignKey(Lead, DEFAULT_ON_DELETE, related_name="discussions")
    note = models.TextField()
    follow_up_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, DEFAULT_ON_DELETE, null=True, related_name="+"
    )

    class Meta(ModelBase.Meta):
        ordering = ("-created_at", "-id")
