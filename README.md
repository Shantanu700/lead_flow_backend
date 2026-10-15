# LeadFlow backend

Django REST API for the LeadFlow CRM (Python 3.14, uv, Celery).

**Frontend repository:** [lead_flow_frontend](https://github.com/Shantanu700/lead_flow_frontend) (Next.js). The app needs both; the steps below run them together.

## Run LeadFlow locally

### Prerequisites

- [Git](https://git-scm.com)
- [Docker](https://docs.docker.com/get-docker/) with Docker Compose (runs the backend, Postgres and Redis)
- [Bun](https://bun.sh) (the frontend's package manager)
- [mkcert](https://github.com/FiloSottile/mkcert) (local HTTPS certificates that browsers trust)

### Steps

1. **Clone both repositories side by side:**
   ```bash
   mkdir leadflow && cd leadflow
   git clone https://github.com/Shantanu700/lead_flow_backend.git backend
   git clone https://github.com/Shantanu700/lead_flow_frontend.git frontend
   ```
2. **Trust local HTTPS certificates** (once per machine; it may ask for your password):
   ```bash
   mkcert -install
   ```
3. **Start the backend:**
   ```bash
   cd backend
   cp .env.example .env
   # Set DJANGO_SECRET_KEY in .env, e.g. to the output of:
   python3 -c "import secrets; print(secrets.token_urlsafe(50))"
   mkdir -p certs
   mkcert -cert-file certs/localhost.pem -key-file certs/localhost-key.pem localhost 127.0.0.1 ::1
   docker compose -f docker/dev/docker-compose.yml up -d --build
   docker logs -f leadflow_dev_web   # wait for "Starting development server", then Ctrl+C
   ```
   The first start creates the database, runs the migrations, loads sample data and prints the demo login (`demo@example.com` and its password; set `DEMO_PASSWORD` in `.env` beforehand to choose it). The API is at https://localhost:8011, with docs at https://localhost:8011/api/schema/swagger-ui/.
4. **Start the frontend** (in a second terminal, from the `leadflow` folder):
   ```bash
   cd frontend
   bun install
   mkdir -p certificates
   mkcert -cert-file certificates/localhost.pem -key-file certificates/localhost-key.pem localhost 127.0.0.1 ::1
   bun dev
   ```
5. **Open https://localhost:3000** and sign in as `demo@example.com` with the password from step 3, or register a new account.

### Stopping and resetting

```bash
cd backend
docker compose -f docker/dev/docker-compose.yml down      # stop; the data is kept
docker compose -f docker/dev/docker-compose.yml down -v   # stop and delete the database
docker exec leadflow_dev_web python manage.py seed_fixtures --reset   # fresh sample data
```

In development the `web` container runs `docker/dev/start.sh`: `create_database`, migrations, `seed_fixtures --if-empty`, then the HTTPS dev server. Restarts keep the data in the `pgdata` volume; Postgres is also reachable from the host on port 5433.

### Useful commands

Run them in the web container (`docker exec -it leadflow_dev_web zsh`):

```bash
python manage.py create_database           # create the role and database if missing
python manage.py seed_fixtures --reset     # replace all leads with fresh sample data
python -m pytest                           # tests
```

## Prod

Copy `docker/prod/.env.example` to `docker/prod/.env` and fill it in, then:
```bash
docker compose -f docker/prod/docker-compose.yml up -d --build   # http://localhost:8020
docker compose -f docker/prod/docker-compose.yml down
```

See `CLAUDE.md` for conventions and the env and migration workflow.
