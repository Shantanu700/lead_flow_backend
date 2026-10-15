from django.urls import path

from modules.leads.api.v1.views import (
    DiscussionAV,
    FollowUpsOverdueAV,
    FollowUpsTodayAV,
    LeadDetailAV,
    LeadListAV,
)

urlpatterns = [
    path("leads/", LeadListAV.as_view()),
    path("leads/<int:pk>/", LeadDetailAV.as_view()),
    path("leads/<int:pk>/discussions/", DiscussionAV.as_view()),
    path("follow-ups/today/", FollowUpsTodayAV.as_view()),
    path("follow-ups/overdue/", FollowUpsOverdueAV.as_view()),
]
