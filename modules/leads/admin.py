from django.contrib import admin

from modules.leads.models import Discussion, Lead


@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    list_display = ("name", "company", "lead_status", "value", "next_follow_up_at")
    list_filter = ("lead_status", "source")
    search_fields = ("name", "company", "phone")


@admin.register(Discussion)
class DiscussionAdmin(admin.ModelAdmin):
    list_display = ("lead", "created_at", "follow_up_at")
