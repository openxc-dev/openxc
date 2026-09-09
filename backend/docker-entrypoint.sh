#!/bin/sh
set -e

echo "Waiting for postgres..."
python - <<'EOF'
import time
import sys
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError

from app.config import settings

engine = create_engine(settings.database_url)
for attempt in range(60):
    try:
        with engine.connect():
            print("Postgres is ready.")
            sys.exit(0)
    except OperationalError:
        time.sleep(1)
print("Postgres did not become ready in time.", file=sys.stderr)
sys.exit(1)
EOF

echo "Running database migrations..."
alembic upgrade head

if [ "${SEED_DEMO_DATA:-false}" = "true" ]; then
    echo "Seeding demo data..."
    python -m app.seed
fi

echo "Starting API server..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
