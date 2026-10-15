"""Fill the database with illustrative sample data, dated relative to now.

JSON fixtures hold fixed dates, so "today's follow-ups" and "won this month"
would go stale; this command builds the same picture on any day:

- an open pipeline shaped like a funnel (New > Contacted > Qualified >
  Proposal Sent), with follow-ups today, overdue and over the next week;
- a year of closed deals that grows month by month, with a win on each day of
  the current week, so every Reports period has bars, a win rate to compare
  and a full mix of lead sources;
- a demo login (demo@example.com) that owns it all.

All names, companies and phone numbers are made up (555-01xx is a fictional
range).
"""

import os
import random
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from modules.leads.models import Discussion, Lead, LeadSource, LeadStatus

DEMO_EMAIL = "demo@example.com"

S = LeadStatus
OPEN_PATH = [S.NEW, S.CONTACTED, S.QUALIFIED, S.PROPOSAL_SENT]

# Note texts per stage; a lead's notes walk through the stages it has reached.
NOTES = {
    S.NEW: [
        "Came in through the website form.",
        "Asked for pricing on the contact form.",
        "Met at the trade expo; wants a call back.",
        "Referred by an existing customer.",
    ],
    S.CONTACTED: [
        "Left a voicemail, will try again.",
        "Intro call: walked through their current process.",
        "Sent the product overview by email.",
        "Spoke briefly; asked to follow up after month end.",
    ],
    S.QUALIFIED: [
        "Budget confirmed, wants a demo.",
        "Demo done; the team liked the reporting.",
        "Finance head decides; needs a case study.",
    ],
    S.PROPOSAL_SENT: [
        "Proposal sent, waiting on sign-off.",
        "Revised the quote with a multi-year discount.",
        "Legal is reviewing the contract.",
    ],
    S.WON: [
        "Signed the annual plan.",
        "Purchase order received.",
        "Kick-off call scheduled for next week.",
    ],
    S.LOST: [
        "Went with a cheaper vendor.",
        "Budget frozen until next year.",
        "Chose to build it in-house.",
    ],
}

# Named leads from the frontend mock-ups: name, company, status, value (₹),
# last note (days ago, hh:mm).
NAMED = [
    ("Priya Sharma", "Acme Corp", S.QUALIFIED, 92000, (0, "10:20")),
    ("Rohan Mehta", "Kite Labs", S.PROPOSAL_SENT, 160000, (2, "16:00")),
    ("Elena Ruiz", "Northwind", S.NEW, 32500, (0, "09:05")),
    ("Daniel Okafor", "Bluefin Studio", S.CONTACTED, 61000, (1, "15:30")),
    ("Mei Tanaka", "Sora Health", S.WON, 124000, (3, "12:00")),
    ("Arjun Nair", "Granite & Co", S.PROPOSAL_SENT, 207500, (3, "11:15")),
    ("Sofia Bianchi", "Lumen Retail", S.LOST, 45000, (7, "14:00")),
    ("Kabir Khan", "Fieldstone", S.NEW, 24000, (0, "11:40")),
    ("Liam Carter", "Harbor Freight Co", S.CONTACTED, 38000, (1, "10:00")),
    ("Ananya Iyer", "Pixel Forge", S.QUALIFIED, 76500, (2, "17:45")),
    ("Noah Fischer", "Brightline", S.NEW, 26000, (0, "08:15")),
    ("Zara Ahmed", "Cedar Finance", S.PROPOSAL_SENT, 143500, (4, "13:10")),
    ("Lucas Moreau", "Atelier Nord", S.WON, 99500, (6, "16:30")),
    ("Isha Reddy", "Monsoon Foods", S.CONTACTED, 42000, (3, "09:40")),
    ("Ethan Brooks", "Quarry Labs", S.QUALIFIED, 105000, (1, "18:20")),
    ("Hana Kim", "Seoul Supply", S.NEW, 19500, (0, "12:10")),
    ("Omar Haddad", "Dune Logistics", S.LOST, 56000, (9, "11:00")),
    ("Chloe Martin", "Petal & Stem", S.CONTACTED, 30500, (0, "09:50")),
    ("Vikram Singh", "Ironleaf", S.PROPOSAL_SENT, 182000, (5, "15:00")),
    ("Grace Lee", "Tidewater", S.QUALIFIED, 69000, (2, "10:30")),
    ("Mateo Garcia", "Sol Energy", S.NEW, 36000, (1, "14:45")),
    ("Aisha Bello", "Lagos Digital", S.CONTACTED, 49000, (4, "12:30")),
    ("Ravi Patel", "Orbit Systems", S.WON, 137500, (4, "17:00")),
    ("Emma Novak", "Vista Travel", S.QUALIFIED, 83000, (0, "10:45")),
    ("Jonas Berg", "Fjord Design", S.NEW, 22000, (3, "16:10")),
    ("Leila Haddad", "Olive Tree Co", S.LOST, 40500, (8, "13:20")),
]

# Follow-ups of named leads: name -> (days from today, hh:mm, done).
# Negative days are overdue.
FOLLOW_UPS = {
    "Isha Reddy": (0, "10:00", True),
    "Priya Sharma": (0, "11:30", True),
    "Hana Kim": (0, "12:15", False),
    "Elena Ruiz": (0, "13:00", False),
    "Daniel Okafor": (0, "15:15", False),
    "Ethan Brooks": (0, "16:00", False),
    "Kabir Khan": (0, "17:00", False),
    "Grace Lee": (0, "18:30", False),
    "Aisha Bello": (-3, "12:00", False),
    "Rohan Mehta": (-2, "11:00", False),
    "Arjun Nair": (-1, "15:00", False),
    "Mateo Garcia": (-1, "10:30", False),
    "Ananya Iyer": (1, "10:00", False),
    "Zara Ahmed": (1, "14:30", False),
    "Liam Carter": (2, "11:00", False),
    "Vikram Singh": (5, "16:00", False),
}
# Follow-ups for generated open leads over the next week: (days, hh:mm).
UPCOMING = [(1, "12:00"), (2, "15:30"), (3, "10:30"), (4, "11:45"), (6, "14:00"), (7, "10:15")]

# Generated open leads per stage, on top of the named ones, so the pipeline
# narrows: New 24 > Contacted 19 > Qualified 14 > Proposal Sent 10.
EXTRA_OPEN = {S.NEW: 18, S.CONTACTED: 14, S.QUALIFIED: 9, S.PROPOSAL_SENT: 6}
# Age (days since created) and value range (₹) per open stage.
OPEN_AGE = {S.NEW: (0, 12), S.CONTACTED: (4, 25), S.QUALIFIED: (10, 40), S.PROPOSAL_SENT: (15, 55)}
OPEN_VALUE = {
    S.NEW: (15000, 80000),
    S.CONTACTED: (25000, 120000),
    S.QUALIFIED: (40000, 250000),
    S.PROPOSAL_SENT: (60000, 450000),
}

SOURCE_WEIGHTS = {
    LeadSource.WEBSITE: 34,
    LeadSource.REFERRAL: 22,
    LeadSource.LINKEDIN: 18,
    LeadSource.COLD_EMAIL: 14,
    LeadSource.EVENTS: 12,
}

FIRST = ["Asha", "Dev", "Meera", "Tom", "Nina", "Karan", "Lena", "Sam", "Riya", "Ben",
         "Tara", "Vivek", "Maya", "Leo", "Diya", "Kiran", "Ivy", "Raj", "Zoe", "Arav",
         "Neha", "Felix", "Sara", "Aditya", "Jia", "Marco", "Pooja", "Hugo", "Anika", "Yusuf"]
LAST = ["Kapoor", "Shah", "Brown", "Das", "Silva", "Joshi", "Wong", "Malik", "Rao", "Evans",
        "Menon", "Costa", "Verma", "Lindqvist", "Bose", "Murphy", "Pillai", "Tanaka", "Gill", "Okoro"]
FIRMS = ["Northpeak", "Blue Heron", "Copperline", "Saffron Labs", "Riverbend", "Tallgrass",
         "Kestrel Co", "Lotus Works", "Ember Media", "Summit Foods", "Indigo Freight",
         "Banyan Health", "Quartz Retail", "Peacock Travel", "Silverline Edu", "Marigold Hotels",
         "Neem Agritech", "Coral Finance", "Teak & Tile", "Monarch Motors"]


def at(day, hhmm):
    "Local datetime `day` days from today at hh:mm."
    h, m = map(int, hhmm.split(":"))
    base = timezone.localtime().replace(hour=h, minute=m, second=0, microsecond=0)
    return base + timedelta(days=day)


class Command(BaseCommand):
    help = "Insert illustrative sample data and a demo login (dev only). --reset clears ALL leads first."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Delete every lead and discussion before seeding.",
        )
        parser.add_argument(
            "--if-empty",
            action="store_true",
            help="Do nothing (successfully) when leads already exist.",
        )
        parser.add_argument("--user", help="Email of an existing user to record as creator.")

    def handle(self, *args, reset=False, if_empty=False, user=None, **options):
        if not settings.DEBUG:
            raise CommandError("seed_fixtures only runs with DJANGO_DEBUG=1.")
        if Lead.unfiltered_objects.exists() and not reset:
            if if_empty:
                self.stdout.write("Leads already exist; seeding skipped.")
                return
            raise CommandError("Leads already exist. Use --reset to replace them.")
        if user:
            owner = get_user_model().objects.filter(email=user.lower()).first()
            if owner is None:
                raise CommandError(f"No user with email {user}.")
        else:
            owner = self.demo_user()

        self.rng = random.Random(2026)  # same data on every run
        self.owner = owner
        self.names = set()
        self.phones = 0
        with transaction.atomic():
            if reset:
                Discussion.unfiltered_objects.all().delete()
                Lead.unfiltered_objects.all().delete()
            n_open = self.seed_named() + self.seed_open()
            n_closed = self.seed_closed()
        self.stdout.write(
            self.style.SUCCESS(f"Seeded {n_open} current and {n_closed} closed sample leads.")
        )

    # Helpers

    def demo_user(self):
        "The demo login: created once; an existing one's password is never changed."
        User = get_user_model()
        demo = User.objects.filter(email=DEMO_EMAIL).first()
        if demo:
            self.stdout.write(f"Demo login {DEMO_EMAIL} exists (password unchanged).")
            return demo
        given = os.environ.get("DEMO_PASSWORD")
        password = given or secrets.token_urlsafe(9)
        demo = User.objects.create_user(DEMO_EMAIL, password, name="Demo User")
        shown = "the DEMO_PASSWORD from .env" if given else password
        self.stdout.write(self.style.SUCCESS(f"Demo login: {DEMO_EMAIL} / {shown} (dev only)."))
        return demo

    def source(self):
        return self.rng.choices(list(SOURCE_WEIGHTS), weights=list(SOURCE_WEIGHTS.values()))[0]

    def new_name(self):
        while True:
            name = f"{self.rng.choice(FIRST)} {self.rng.choice(LAST)}"
            if name not in self.names:
                self.names.add(name)
                return name

    def next_phone(self):
        "555-0100 to 555-0199 only (the fictional range); later leads get none."
        self.phones += 1
        return f"555-01{self.phones - 1:02d}" if self.phones <= 100 else ""

    def add_lead(self, created, **fields):
        lead = Lead.objects.create(created_by=self.owner, **fields)
        Lead.objects.filter(pk=lead.pk).update(created_at=created)  # auto_now_add
        return lead

    def add_note(self, lead, when, note, follow_up_at=None):
        d = Discussion.objects.create(
            lead=lead, note=note, follow_up_at=follow_up_at, created_by=self.owner
        )
        Discussion.objects.filter(pk=d.pk).update(created_at=when)

    def add_notes(self, lead, status, created, last, follow_up_at=None):
        """2-5 notes walking through the stages the lead reached: a first
        response 1-8h after it came in, one note per later stage, the newest
        (with the follow-up, if any) at `last`."""
        if status in OPEN_PATH:
            stages = OPEN_PATH[: OPEN_PATH.index(status) + 1]
        else:  # closed after reaching Contacted..Proposal Sent
            stages = [*OPEN_PATH[: self.rng.randint(2, 4)], status]
        stages = stages[-4:]
        first = min(created + timedelta(hours=self.rng.randint(1, 8)), last)
        self.add_note(lead, first, self.rng.choice(NOTES[stages[0]]))
        later = stages[1:] or stages
        step = (last - first) / len(later)
        for i, stage in enumerate(later):
            newest = i == len(later) - 1
            self.add_note(
                lead,
                last if newest else first + step * (i + 1),
                self.rng.choice(NOTES[stage]),
                follow_up_at=follow_up_at if newest else None,
            )

    # Data

    def seed_named(self):
        now = timezone.now()
        for name, company, status, value, (ago, hhmm) in NAMED:
            self.names.add(name)
            last = min(at(-ago, hhmm), now - timedelta(minutes=5))
            created = last - timedelta(days=self.rng.randint(3, 20))
            fu = FOLLOW_UPS.get(name)
            follow = at(fu[0], fu[1]) if fu else None
            lead = self.add_lead(
                created,
                name=name,
                company=company,
                phone=self.next_phone(),
                lead_status=status,
                source=self.source(),
                value=value,
                next_follow_up_at=follow,
                follow_up_done_at=now if fu and fu[2] else None,
                closed_at=last if status in (S.WON, S.LOST) else None,
            )
            self.add_notes(lead, status, created, last, follow)
        return len(NAMED)

    def seed_open(self):
        "Generated open leads; some past New have a follow-up over the next week."
        now = timezone.now()
        upcoming = iter(UPCOMING)
        count = 0
        for status, n in EXTRA_OPEN.items():
            lo, hi = OPEN_AGE[status]
            for _ in range(n):
                created = now - timedelta(days=self.rng.randint(lo, hi), hours=self.rng.randint(1, 10))
                last = min(
                    created + timedelta(days=self.rng.randint(0, 6), hours=3),
                    now - timedelta(minutes=30),
                )
                fu = next(upcoming, None) if status != S.NEW and self.rng.random() < 0.4 else None
                follow = at(*fu) if fu else None
                lead = self.add_lead(
                    created,
                    name=self.new_name(),
                    company=self.rng.choice(FIRMS),
                    phone=self.next_phone(),
                    lead_status=status,
                    source=self.source(),
                    value=self.rng.randrange(*OPEN_VALUE[status], 500),
                    next_follow_up_at=follow,
                )
                self.add_notes(lead, status, created, last, follow)
                count += 1
        return count

    def seed_closed(self):
        """A year of closed deals, more each month, about 60/40 won/lost; plus
        a win on every day of this week so far and a mix last week, so the
        Week, Month and Quarter reports all have bars and a win rate to compare."""
        now = timezone.localtime()
        closes = []  # (closed_at, status)
        for months_ago in range(12, 0, -1):
            month = (now.replace(day=1) - timedelta(days=31 * months_ago - 15)).replace(day=1)
            wins = round(1 + (12 - months_ago) * 0.3)  # 1 a month rising to 4
            for k in range(wins + round(wins * 0.6)):
                when = month + timedelta(days=self.rng.randint(0, 27), hours=self.rng.randint(10, 18))
                closes.append((when, S.WON if k < wins else S.LOST))
        week = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=now.weekday())
        for d in range(now.weekday() + 1):  # Monday up to today
            closes.append((week + timedelta(days=d, hours=self.rng.randint(10, 12)), S.WON))
        if now.weekday():  # one loss this week too, so its win rate isn't 100%
            closes.append((week + timedelta(hours=16), S.LOST))
        last_week = week - timedelta(days=7)
        closes += [
            (last_week + timedelta(days=1, hours=11), S.WON),
            (last_week + timedelta(days=2, hours=15), S.WON),
            (last_week + timedelta(days=3, hours=12), S.WON),
            (last_week + timedelta(days=4, hours=16), S.LOST),
        ]

        for closed, status in closes:
            closed = min(closed, now - timedelta(minutes=10))
            created = closed - timedelta(days=self.rng.randint(10, 45), hours=self.rng.randint(0, 9))
            lead = self.add_lead(
                created,
                name=self.new_name(),
                company=self.rng.choice(FIRMS),
                lead_status=status,
                source=self.source(),
                value=self.rng.randrange(40000, 450000, 500),
                closed_at=closed,
            )
            self.add_notes(lead, status, created, closed)
        return len(closes)
