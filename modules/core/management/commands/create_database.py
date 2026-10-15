"""Create the app's Postgres role and database when they don't exist yet.

The target (user, password, database) comes from DATABASE_URL; the server is
reached as an admin through DATABASE_ADMIN_URL. Safe to run any number of
times: it only creates what is missing.
"""

import os
import time
from urllib.parse import unquote, urlparse

import psycopg
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from psycopg import sql


class Command(BaseCommand):
    help = "Create the DATABASE_URL role (with CREATEDB, for tests) and database if missing (dev only)."

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("create_database only runs with DJANGO_DEBUG=1.")
        admin_url = os.environ.get("DATABASE_ADMIN_URL")
        if not admin_url:
            raise CommandError("Set DATABASE_ADMIN_URL (an admin login to the Postgres server).")
        db = urlparse(os.environ["DATABASE_URL"])
        user, password = unquote(db.username or ""), unquote(db.password or "")
        name = db.path.lstrip("/")

        with self.connect(admin_url) as conn:
            # CREATEDB lets the test runner make its own test database.
            role = conn.execute(
                "SELECT rolcreatedb FROM pg_roles WHERE rolname = %s", [user]
            ).fetchone()
            if role is None:
                conn.execute(
                    sql.SQL("CREATE ROLE {} LOGIN CREATEDB PASSWORD {}").format(
                        sql.Identifier(user), sql.Literal(password)
                    )
                )
                self.stdout.write(self.style.SUCCESS(f"Created role {user}."))
            else:
                if not role[0]:
                    conn.execute(sql.SQL("ALTER ROLE {} CREATEDB").format(sql.Identifier(user)))
                self.stdout.write(f"Role {user} exists.")
            if conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", [name]).fetchone():
                self.stdout.write(f"Database {name} exists.")
            else:
                conn.execute(
                    sql.SQL("CREATE DATABASE {} OWNER {}").format(
                        sql.Identifier(name), sql.Identifier(user)
                    )
                )
                self.stdout.write(self.style.SUCCESS(f"Created database {name}."))

    def connect(self, url, wait=30):
        "Admin connection, retried while the server starts up."
        for attempt in range(wait):
            try:
                return psycopg.connect(url, autocommit=True)
            except psycopg.OperationalError as e:
                if attempt == wait - 1:
                    raise CommandError(f"Cannot reach Postgres: {e}") from e
                time.sleep(1)
