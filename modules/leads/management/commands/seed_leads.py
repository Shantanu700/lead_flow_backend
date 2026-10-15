"""Fill the database with illustrative sample leads, dated relative to now.

JSON fixtures hold fixed dates, so "today's follow-ups" and "won this month"
would go stale; this command builds the same picture on any day. All names,
companies and phone numbers are made up (555-01xx is a fictional range).
"""

import random
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from modules.leads.models import Discussion, Lead, LeadSource, LeadStatus

NOTE = {
    LeadStatus.NEW: "Came in through the website form.",
    LeadStatus.CONTACTED: "Left a voicemail, will try again.",
    LeadStatus.QUALIFIED: "Budget confirmed, wants a demo.",
    LeadStatus.PROPOSAL_SENT: "Proposal sent, waiting on sign-off.",
    LeadStatus.WON: "Signed the annual plan.",
    LeadStatus.LOST: "Went with a cheaper vendor.",
}
FIRST_NOTE = "Intro call: walked through their current process."

# Current pipeline: name, company, status, value (₹), last note (days ago, hh:mm).
CURRENT = [
    ("Priya Sharma", "Acme Corp", "Qualified", 18400, (0, "10:20")),
    ("Rohan Mehta", "Kite Labs", "Proposal Sent", 32000, (2, "16:00")),
    ("Elena Ruiz", "Northwind", "New", 6500, (0, "09:05")),
    ("Daniel Okafor", "Bluefin Studio", "Contacted", 12200, (1, "15:30")),
    ("Mei Tanaka", "Sora Health", "Won", 24800, (3, "12:00")),
    ("Arjun Nair", "Granite & Co", "Proposal Sent", 41500, (3, "11:15")),
    ("Sofia Bianchi", "Lumen Retail", "Lost", 9000, (7, "14:00")),
    ("Kabir Khan", "Fieldstone", "New", 4800, (0, "11:40")),
    ("Liam Carter", "Harbor Freight Co", "Contacted", 7600, (1, "10:00")),
    ("Ananya Iyer", "Pixel Forge", "Qualified", 15300, (2, "17:45")),
    ("Noah Fischer", "Brightline", "New", 5200, (0, "08:15")),
    ("Zara Ahmed", "Cedar Finance", "Proposal Sent", 28700, (4, "13:10")),
    ("Lucas Moreau", "Atelier Nord", "Won", 19900, (6, "16:30")),
    ("Isha Reddy", "Monsoon Foods", "Contacted", 8400, (3, "09:40")),
    ("Ethan Brooks", "Quarry Labs", "Qualified", 21000, (1, "18:20")),
    ("Hana Kim", "Seoul Supply", "New", 3900, (0, "12:10")),
    ("Omar Haddad", "Dune Logistics", "Lost", 11200, (9, "11:00")),
    ("Chloe Martin", "Petal & Stem", "Contacted", 6100, (0, "09:50")),
    ("Vikram Singh", "Ironleaf", "Proposal Sent", 36400, (5, "15:00")),
    ("Grace Lee", "Tidewater", "Qualified", 13800, (2, "10:30")),
    ("Mateo Garcia", "Sol Energy", "New", 7200, (1, "14:45")),
    ("Aisha Bello", "Lagos Digital", "Contacted", 9800, (4, "12:30")),
    ("Ravi Patel", "Orbit Systems", "Won", 27500, (4, "17:00")),
    ("Emma Novak", "Vista Travel", "Qualified", 16600, (0, "10:45")),
    ("Jonas Berg", "Fjord Design", "New", 4400, (3, "16:10")),
    ("Leila Haddad", "Olive Tree Co", "Lost", 8100, (8, "13:20")),
]

# Follow-ups: name -> (days from today, hh:mm, done). Negative = overdue.
FOLLOW_UPS = {
    "Priya Sharma": (0, "11:30", True),
    "Hana Kim": (0, "12:15", False),
    "Elena Ruiz": (0, "13:00", False),
    "Daniel Okafor": (0, "15:15", False),
    "Ethan Brooks": (0, "16:00", False),
    "Kabir Khan": (0, "17:00", False),
    "Grace Lee": (0, "18:00", False),
    "Rohan Mehta": (-2, "11:00", False),
    "Arjun Nair": (-1, "15:00", False),
    "Ananya Iyer": (1, "10:00", False),
    "Zara Ahmed": (1, "14:30", False),
    "Liam Carter": (2, "11:00", False),
    "Vikram Singh": (5, "16:00", False),
}

# Source mix, roughly 34 / 22 / 18 / 14 / 12 %.
SOURCES = (
    [LeadSource.WEBSITE] * 17
    + [LeadSource.REFERRAL] * 11
    + [LeadSource.LINKEDIN] * 9
    + [LeadSource.COLD_EMAIL] * 7
    + [LeadSource.EVENTS] * 6
)

FIRST = ["Asha", "Dev", "Meera", "Tom", "Nina", "Karan", "Lena", "Sam", "Riya", "Ben",
         "Tara", "Vivek", "Maya", "Leo", "Diya", "Omar", "Ivy", "Raj", "Zoe", "Arav"]
LAST = ["Kapoor", "Shah", "Brown", "Das", "Silva", "Joshi", "Wong", "Malik", "Rao", "Evans"]
FIRMS = ["Northpeak", "Blue Heron", "Copperline", "Saffron Labs", "Riverbend", "Tallgrass",
         "Kestrel Co", "Lotus Works", "Ember Media", "Summit Foods"]


def at(day, hhmm):
    "Local datetime `day` days from today at hh:mm."
    h, m = map(int, hhmm.split(":"))
    base = timezone.localtime().replace(hour=h, minute=m, second=0, microsecond=0)
    return base + timedelta(days=day)


class Command(BaseCommand):
    help = "Insert illustrative sample leads (dev only). --reset clears ALL leads first."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Delete every lead and discussion before seeding.",
        )
        parser.add_argument("--user", help="Email of the user to record as creator.")

    def handle(self, *args, reset=False, user=None, **options):
        if not settings.DEBUG:
            raise CommandError("seed_leads only runs with DJANGO_DEBUG=1.")
        if Lead.unfiltered_objects.exists() and not reset:
            raise CommandError("Leads already exist. Use --reset to replace them.")
        owner = get_user_model().objects.filter(email=user.lower()).first() if user else None
        if user and owner is None:
            raise CommandError(f"No user with email {user}.")

        rng = random.Random(2026)  # same data on every run
        with transaction.atomic():
            if reset:
                Discussion.unfiltered_objects.all().delete()
                Lead.unfiltered_objects.all().delete()
            current = self.seed_current(rng, owner)
            history = self.seed_history(rng, owner)
        self.stdout.write(
            self.style.SUCCESS(f"Seeded {current} current and {history} closed sample leads.")
        )

    def add_lead(self, owner, created, **fields):
        lead = Lead.objects.create(created_by=owner, **fields)
        Lead.objects.filter(pk=lead.pk).update(created_at=created)  # auto_now_add
        return lead

    def add_note(self, lead, owner, when, note, follow_up_at=None):
        d = Discussion.objects.create(
            lead=lead, note=note, follow_up_at=follow_up_at, created_by=owner
        )
        Discussion.objects.filter(pk=d.pk).update(created_at=when)

    def seed_current(self, rng, owner):
        now = timezone.now()
        for i, (name, company, status, value, (ago, hhmm)) in enumerate(CURRENT):
            last = min(at(-ago, hhmm), now - timedelta(minutes=5))
            created = last - timedelta(days=rng.randint(3, 20))
            fu = FOLLOW_UPS.get(name)
            follow = at(fu[0], fu[1]) if fu else None
            closed = last if status in ("Won", "Lost") else None
            lead = self.add_lead(
                owner,
                created,
                name=name,
                company=company,
                phone=f"555-01{i:02d}",
                lead_status=status,
                source=SOURCES[i % len(SOURCES)],
                value=value,
                next_follow_up_at=follow,
                follow_up_done_at=now if fu and fu[2] else None,
                closed_at=closed,
            )
            # First response a few hours after the lead came in, then the latest note.
            self.add_note(lead, owner, created + timedelta(hours=rng.randint(1, 6)), FIRST_NOTE)
            self.add_note(lead, owner, last, NOTE[status], follow_up_at=follow)
        return len(CURRENT)

    def seed_history(self, rng, owner):
        "Closed deals over the past year, so Reports has months and quarters to show."
        now = timezone.now()
        count = 48
        for i in range(count):
            closed = now - timedelta(days=rng.randint(8, 330), hours=rng.randint(0, 23))
            created = closed - timedelta(days=rng.randint(5, 40))
            status = LeadStatus.WON if rng.random() < 0.6 else LeadStatus.LOST
            lead = self.add_lead(
                owner,
                created,
                name=f"{rng.choice(FIRST)} {rng.choice(LAST)}",
                company=rng.choice(FIRMS),
                lead_status=status,
                source=SOURCES[(i * 7) % len(SOURCES)],
                value=rng.randrange(6000, 46000, 100),
                closed_at=closed,
            )
            self.add_note(lead, owner, created + timedelta(hours=rng.randint(1, 30)), FIRST_NOTE)
            self.add_note(lead, owner, closed, NOTE[status])
        return count
