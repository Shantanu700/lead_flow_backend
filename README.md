# LeadFlow backend

Django REST API for the LeadFlow CRM (Python 3.14, uv, Celery). It uses the shared Postgres and Redis containers on `dev_db_network`.

## First run

1. Start the shared database stack (`~/3.0/dev/postgres.yml` and `redis.yml`).
2. Copy `.env.example` to `.env` and fill in `DJANGO_SECRET_KEY` and the `leadflow` DB password.
3. Start the dev stack:
   ```bash
   docker compose -f docker/dev/docker-compose.yml up -d --build
   ```
4. Open a shell in the dev container:
   ```bash
   docker exec -it leadflow_dev_web zsh
   ```
5. Create the local HTTPS certificate on the host (once per machine). `mkcert -install` asks for your password; it makes browsers trust the cert:
   ```bash
   mkcert -install
   mkcert -cert-file certs/localhost.pem -key-file certs/localhost-key.pem localhost 127.0.0.1 ::1
   ```
6. Inside the container, set up the database and start the HTTPS server:
   ```bash
   python manage.py makemigrations && python manage.py migrate
   python manage.py runsslserver 0.0.0.0:8001 --certificate certs/localhost.pem --key certs/localhost-key.pem
   ```
   The API is at https://localhost:8011, with docs at https://localhost:8011/api/schema/swagger-ui/. Plain `runserver 0.0.0.0:8000` still serves http://localhost:8010.

## Prod

Copy `docker/prod/.env.example` to `docker/prod/.env` and fill it in, then:
```bash
docker compose -f docker/prod/docker-compose.yml up -d --build   # http://localhost:8020
docker compose -f docker/prod/docker-compose.yml down
```

See `CLAUDE.md` for conventions and the env and migration workflow.
