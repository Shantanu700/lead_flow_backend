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
  - Inside it run `python manage.py runserver 0.0.0.0:8000`. It's reachable at `localhost:8010`.
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
