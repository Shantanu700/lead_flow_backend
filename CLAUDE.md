# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Django + DRF API for **LeadFlow**, a single-screen CRM. The frontend (Next.js) lives in `../frontend`, and its `README.md` is the product spec (leads, discussions, follow-ups, business rules, REST contract). The skeleton mirrors `~/projects/certifier_reloaded_backend` and `~/projects/munim_backend`.

## Running

Python 3.14 with uv. Everything runs in Docker.
- **Dev** brings its own services in `docker/dev/docker-compose.yml`: Postgres 17 (`postgres:5432`, host port 5433, `pgdata` volume) and Redis 8 (`redis:6379`, index 0). The app's role and database are `leadflow` / `leadflow_dev`. Redis is both the Celery broker and the Django cache.
- **Prod** still uses the shared Postgres and Redis on `dev_db_network` (`postgres_db`, `redis`; database `leadflow_prod`, Redis index 3), from `~/3.0/dev/postgres.yml` and `redis.yml`.

- Dev up: `docker compose -f docker/dev/docker-compose.yml up -d --build`
  - Only `DJANGO_SECRET_KEY` must be filled in after `cp .env.example .env`.
  - The `web` container runs `docker/dev/start.sh`: `create_database`, `makemigrations` + `migrate`, `seed_fixtures --if-empty`, then the HTTPS dev server (`runsslserver` on 8001, using `certs/` when present) at `https://localhost:8011`. Django's autoreloader picks up code and `.env` changes.
  - For commands, use `docker exec -it leadflow_dev_web zsh` (or open it as a VS Code devcontainer). `docker compose ... down -v` wipes the database volume.
  - Plain HTTP still works: `python manage.py runserver 0.0.0.0:8000` serves `http://localhost:8010`.
  - `django-sslserver-v2` is a dev dependency. `sslserver` is added to `INSTALLED_APPS` only when `DJANGO_DEBUG=1`, so the prod image doesn't include it.
  - `certs/` holds an mkcert certificate for `localhost`, `127.0.0.1` and `::1`. It's gitignored and dockerignored; regenerate it with `mkcert -cert-file certs/localhost.pem -key-file certs/localhost-key.pem localhost 127.0.0.1 ::1`. Browsers trust it once `mkcert -install` has been run on the machine.
  - `worker` and `beat` run Celery under `watchfiles`.
- Prod up: `docker compose -f docker/prod/docker-compose.yml up -d --build`
  - A one-shot `migrate` service runs first, then uvicorn serves on `localhost:8020`.
  - `web` has a healthcheck on `/api/health/`.
- Tests: `python -m pytest`, run inside the dev container. A single test: `python -m pytest tests/test_health.py::test_health_reports_ok`.
- API docs: `/api/schema/swagger-ui/` and `/api/schema/redoc/`.

## Environment

- **Dev:** settings come from `backend/.env`, which `config/settings.py` reads itself with `load_dotenv(override=True)`. Compose does not inject them.
  - Saving `.env` makes runserver reload (`modules/core/apps.py` watches it), and `watchfiles` restarts Celery.
  - You never need to restart the container for an env change.
- **Prod:** settings come from `docker/prod/.env` through compose `env_file`. After editing it, run the prod `up -d` again.
- Both real `.env` files are gitignored, and `**/.env` is dockerignored. Only the `.env.example` templates are committed.
- `create_database` (`modules/core/management/commands/`, dev only) logs in with `DATABASE_ADMIN_URL` (the compose Postgres superuser) and creates the `DATABASE_URL` role, with CREATEDB so pytest can make its test database, and the database, when missing.
- `DJANGO_SECRET_KEY`, `DATABASE_URL` and `REDIS_URL` are required, so settings fail at import without them.

## Migrations

`**/migrations/**` is gitignored, as in certifier. After cloning, or after changing models, run `python manage.py makemigrations && python manage.py migrate` in the dev container.

The prod image copies whatever migration files are on disk, so run `makemigrations` in dev before building prod.

## Conventions (base/)

- **Models:** subclass `base.model.ModelBase`. It adds `uuid`, `status`, `created_at` and `updated_at`.
  - Deletes are soft: set `status = Status.DELETED`. `objects` hides soft-deleted rows; `unfiltered_objects` includes them.
  - Foreign keys use `base.defaults.DEFAULT_ON_DELETE`.
- **Views:** subclass `base.views.BaseAV` (an APIView).
  - Every endpoint requires authentication unless the view sets `authentication = False`, or a per-method dict such as `{"post": False}`.
  - A handler can return a dict, list, str or pydantic model; it's wrapped in a response with the status from `STATUS_MAPPING` (POST returns 201).
  - `self.fail(msg)` refuses the request with 400 `{"msg": msg}` (pass a status, e.g. 401, to override). `self.success(msg)` returns `{"msg": msg}`.
- **Serializers:** subclass `base.serializers.BaseSerializer`. It supports `fields=` and `exclude=` at runtime, plus `dynamic_keys`.
- **Errors:** go through `base.exceptions.exception_handler`. Invalid input is always 400: Django `ValidationError` becomes `{"msg": [...]}`, and `SerializerError` returns the errors per field. Not signed in is 401, a missing record 404.
- **New feature module:** create `modules/<app>/` with `api/v1/{serializers,views,urls}.py`. Keep `api/` and `api/v1/` as namespace packages with no `__init__.py`. Add `"modules.<app>"` to `LOCAL_APPS` and `include("modules.<app>.api.v1.urls")` in `config/urls.py`.
- **User model:** `AUTH_USER_MODEL = "core.User"` (`modules/core/models.py`).
- **CSRF:** stays enabled, unlike certifier and munim. CORS allows only `CORS_ALLOWED_ORIGINS`.

## Auth

Email and password with Django sessions. There's no Google sign-in. Endpoints live in `modules/core/api/v1/`, mounted at `/core/`:

- `GET /core/csrf/` (public): returns `{"csrf_token"}` and sets the `csrftoken` cookie.
- `POST /core/register/` (public): body `{name, email, password}`.
  - Success: signs the new user in and returns 201 with the user.
  - Invalid: returns 400 with a dict of errors per field. A duplicate email is checked case-insensitively, and the password goes through Django's validators.
- `POST /core/login/` (public): body `{email, password}`. Returns 201 with the user, or 401 `{"msg": "Email or password is incorrect."}`.
- `GET /core/login/`: returns the current user, or 401 when signed out.
- `DELETE /core/login/` (public): signs out and returns 200 `{"msg": "Signed out."}`.

`USERNAME_FIELD = "email"`. `UserManager.create_user(email, password, **extra)` stores the email lowercase and mirrors it into `username` for the stock admin.

CSRF stays on:
- Anonymous POSTs (login, register) don't need a token, because DRF only enforces CSRF for an authenticated session.
- Every authenticated write must send `X-CSRFToken`.
- `login()` and `logout()` rotate the token, so clients re-fetch `/core/csrf/` after either.

Origins come from `.env`. In dev the frontend runs at `https://localhost:3000`. Both servers use HTTPS on `localhost`, so the browser treats them as the same site and the default `SameSite=Lax` session cookie works.

The schema is OpenAPI 3.1, because the pydantic `Literal` types in `base/types.py` produce `const`. The frontend generates its client from `/api/schema/`.

## Leads API

`modules/leads/`, mounted at `/api/`. Every endpoint needs a signed-in user. Leads are one shared team list, and each lead and note records `created_by`.

- `GET /api/leads/`: paginated `{count, next, previous, results}`. Filtering, search and sorting all happen on the server.
  - `?page=` is 1-based. `?page_size=` defaults to 10, with a maximum of 50. A page past the end returns 404.
  - `?status=` takes one of the six statuses.
  - `?q=` searches name, company, phone and the latest note.
  - `?ordering=recent|value|name`:
    - `recent` (the default) puts the lead touched last first: its newest note, else when it was created.
    - `value` sorts highest first.
    - `name` sorts A to Z, ignoring case.
- `POST /api/leads/`: body `{name, company?, phone?, source?, value?}`. The name is trimmed and required. Status is always `New`, and any `status` sent is ignored.
- `GET /api/leads/{id}/` and `PUT /api/leads/{id}/`: PUT takes any of `name, company, phone, status, source, value, next_follow_up_at, follow_up_done`. Only the fields sent change. The API uses PUT for updates, never PATCH.
  - `follow_up_done: true` ticks off the follow-up by setting `follow_up_done_at`.
  - Setting a new `next_follow_up_at`, directly or through a discussion, reopens it.
  - Moving to Won or Lost stamps `closed_at`. Reopening clears it.
- `GET /api/leads/{id}/discussions/`: notes, newest first.
- `POST /api/leads/{id}/discussions/`: body `{note, follow_up_at?}`. Returns `{discussion, lead}`.
  - A follow-up also sets the lead's `next_follow_up_at`, in the same transaction.
  - A follow-up in the past is rejected with 400.
- `GET /api/follow-ups/today/`: leads whose `next_follow_up_at` falls today in `TIME_ZONE` (Asia/Kolkata), earliest first.
- `GET /api/follow-ups/overdue/`: open leads (not Won or Lost) whose follow-up was due before today and isn't done.
- `GET /api/follow-ups/upcoming/`: follow-ups in the 7 days after today that aren't done.

### Stats, one endpoint per tab

Each endpoint returns only the figures its tab shows. They're computed with aggregate queries (`modules/leads/api/v1/stats.py`), and no lead rows are sent. The Follow-ups tab needs no stats endpoint, because its counts are the lengths of its three lists.

- `GET /api/stats/dashboard/`: `open_value`, `active_leads`, `conversion_rate` (Won as a % of all leads), `avg_first_response_hours` (lead created to its first note), `won_this_month`, `by_status`.
- `GET /api/stats/leads/`: `open_value`, `open_leads`, `avg_value`, `win_rate` (Won as a % of Won + Lost), `by_status`.
- `GET /api/stats/reports/?period=week|month|quarter`:
  - Fields: `revenue`, `deals_won`, `avg_deal`, `avg_days_to_close`, `win_rate`, `prev_win_rate`, `bars`, `funnel` (count and value per status, all leads), `leads`, `sources`.
  - Periods use the app timezone. A week runs Monday to Sunday with daily bars. A month has bars for the last 6 months. A quarter is a calendar quarter, with bars for Q1 to Q4 of the year.

Model notes:
- `ModelBase.status` is the soft-delete flag. The pipeline stage is therefore `Lead.lead_status`, and serializers expose it as `status`.
- `last_note` is never stored. `with_last_note()` annotates it from the newest discussion, so read leads through that helper.
- `value` is whole rupees. `source` is one of `LeadSource`.

### Sample data

`python manage.py seed_fixtures`, run in the dev container (and automatically by `start.sh` on an empty database), fills the database with illustrative data so every chart has something to show, and creates the demo login `demo@example.com`.
- **Demo login:** its password is `DEMO_PASSWORD` from `.env`, or a random one printed once when the account is created. An existing account's password is never changed, and it owns the seeded leads.
- **Pipeline:** 67 open leads shaped like a funnel (New 24, Contacted 19, Qualified 14, Proposal Sent 10), including the 26 named leads the frontend mock-ups use. Each has 2 to 5 notes that follow its stage. Follow-ups fall today (8, 2 done), overdue (4) and over the next week.
- **History:** about 65 closed deals over the past year, about 60/40 won/lost, rising month by month, plus a win on each day of the current week and a mix last week. Every Reports period (week, month, quarter) has bars, a win rate and a previous-period win rate, and recent leads come from all five sources.
- **Dates:** everything is dated relative to now, so the data looks right whatever day it runs. Static JSON fixtures would go stale.
- **Fake contact data:** phones use the fictional 555-01xx range.

Options and safeguards:
- It only runs with `DJANGO_DEBUG=1`, and it refuses if any leads already exist. `--if-empty` turns that refusal into a quiet no-op (used by `start.sh`).
- `--reset` deletes every lead and discussion first.
- `--user <email>` records that user as the creator.
