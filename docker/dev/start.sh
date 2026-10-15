#!/bin/sh
# web's start-up: database, migrations, sample data (only into an empty
# database), then the HTTPS dev server on :8001 (https://localhost:8011).
set -e
python manage.py create_database
python manage.py makemigrations --noinput  # migrations are gitignored
python manage.py migrate --noinput
python manage.py seed_fixtures --if-empty

if [ -f certs/localhost.pem ] && [ -f certs/localhost-key.pem ]; then
  exec python manage.py runsslserver 0.0.0.0:8001 \
    --certificate certs/localhost.pem --key certs/localhost-key.pem
fi
echo "No mkcert certificate in certs/: using sslserver's built-in one, which browsers won't trust (see README)."
exec python manage.py runsslserver 0.0.0.0:8001
