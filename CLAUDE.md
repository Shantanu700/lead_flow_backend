# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Django + DRF API for **LeadFlow**, a single-screen CRM. The frontend (Next.js) lives in `../frontend`, and its `README.md` is the product spec (leads, discussions, follow-ups, business rules, REST contract). The skeleton mirrors `~/projects/certifier_reloaded_backend` and `~/projects/munim_backend`.

## Running

Python 3.14 with uv. Everything runs in Docker on the shared `dev_db_network`:
- Postgres: `postgres_db:5432`. Dev uses database `leadflow_dev`, prod uses `leadflow_prod`, and the role is `leadflow`.
- Redis: `redis:6379`. Dev uses index 2, prod uses index 3. Redis is both the Celery broker and the Django cache.

Those shared containers come from `~/3.0/dev/postgres.yml` and `redis.yml`. They must be running first.

- Dev up: `docker compose -f docker/dev/docker-compose.yml up -d --build`
  - The `web` container idles. Open it as a VS Code devcontainer, or use `docker exec -it leadflow_dev_web zsh`.
  - Inside it, start the HTTPS dev server: `python manage.py runsslserver 0.0.0.0:8001 --certificate certs/localhost.pem --key certs/localhost-key.pem`. It's reachable at `https://localhost:8011`.
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
  - `self.fail(msg)` raises a 409 and `self.success(msg)` returns `{"msg": msg}`.
- **Serializers:** subclass `base.serializers.BaseSerializer`. It supports `fields=` and `exclude=` at runtime, plus `dynamic_keys`.
- **Errors:** go through `base.exceptions.exception_handler`. Django `ValidationError` becomes 409 `{"msg": [...]}` and `SerializerError` becomes 418.
- **New feature module:** create `modules/<app>/` with `api/v1/{serializers,views,urls}.py`. Keep `api/` and `api/v1/` as namespace packages with no `__init__.py`. Add `"modules.<app>"` to `LOCAL_APPS` and `include("modules.<app>.api.v1.urls")` in `config/urls.py`.
- **User model:** `AUTH_USER_MODEL = "core.User"` (`modules/core/models.py`).
- **CSRF:** stays enabled, unlike certifier and munim. CORS allows only `CORS_ALLOWED_ORIGINS`.

## Auth

Email and password with Django sessions. There's no Google sign-in. Endpoints live in `modules/core/api/v1/`, mounted at `/core/`:

- `GET /core/csrf/` (public): returns `{"csrf_token"}` and sets the `csrftoken` cookie.
- `POST /core/register/` (public): body `{name, email, password}`.
  - Success: signs the new user in and returns 201 with the user.
  - Invalid: returns 418 with a dict of errors per field. A duplicate email is checked case-insensitively, and the password goes through Django's validators.
- `POST /core/login/` (public): body `{email, password}`. Returns 201 with the user, or 409 `{"msg": "Email or password is incorrect."}`.
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

- `GET /api/leads/`: all leads, newest first. Optional `?status=` (one of the six) and `?q=` (name, company or phone). Not paginated yet.
- `POST /api/leads/`: body `{name, company?, phone?, source?, value?}`. The name is trimmed and required. Status is always `New`, and any `status` sent is ignored.
- `GET /api/leads/{id}/` and `PUT /api/leads/{id}/`: PUT takes any of `name, company, phone, status, source, value, next_follow_up_at`. Only the fields sent change. Send `next_follow_up_at: null` to mark a follow-up done. The API uses PUT for updates, never PATCH.
- `GET /api/leads/{id}/discussions/`: notes, newest first.
- `POST /api/leads/{id}/discussions/`: body `{note, follow_up_at?}`. Returns `{discussion, lead}`.
  - A follow-up also sets the lead's `next_follow_up_at`, in the same transaction.
  - A follow-up in the past is rejected with 418.
- `GET /api/follow-ups/today/`: leads whose `next_follow_up_at` falls today in `TIME_ZONE` (Asia/Kolkata), earliest first.
- `GET /api/follow-ups/overdue/`: open leads (not Won or Lost) whose follow-up was due before today.

Model notes:
- `ModelBase.status` is the soft-delete flag. The pipeline stage is therefore `Lead.lead_status`, and serializers expose it as `status`.
- `last_note` is never stored. `with_last_note()` annotates it from the newest discussion, so read leads through that helper.
- `value` is whole rupees. `source` is one of `LeadSource`.
