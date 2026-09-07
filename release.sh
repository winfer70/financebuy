#!/bin/bash
# release.sh - tickerTap production release
# Run from a trusted local dev machine. Merges tradingAI0.1 -> main, tags, and deploys to the configured target host.
# Usage: NODE_HOST=your-server-hostname NODE_USER=your-ssh-user TARGET_DIR=/path/to/deployment ./release.sh
set -e

NODE_HOST="${NODE_HOST:-your-server-hostname}"
NODE_USER="${NODE_USER:-<YOUR_SSH_USER>}"
TARGET_DIR="${TARGET_DIR:-/path/to/deployment}"
INTEGRATION_BRANCH="tradingAI0.1"
DB_SERVICE="db"
# Must match the compose file actually deployed on TARGET_DIR (labserver setup
# uses docker-compose.labserver.yml, not the bare default docker-compose.yml —
# running `docker compose` without -f here would target the wrong stack).
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.labserver.yml}"
KUMA_PUSH_URL="${KUMA_PUSH_URL:-}"  # Optional Push monitor URL

# ── 1. Tag and push ──────────────────────────────────────────────────────────
echo "[1/6] Merging $INTEGRATION_BRANCH -> main..."
git stash push -- graphify-out/ 2>/dev/null || true
git checkout main && git pull origin main
git merge "$INTEGRATION_BRANCH" --no-edit
VERSION="v$(date +%Y.%m.%d-%H%M)"
git tag -a "$VERSION" -m "Release $VERSION"
git push origin main --tags
git checkout "$INTEGRATION_BRANCH"
git stash pop 2>/dev/null || true
echo "Tagged $VERSION"

# ── 2-6. Remote deploy ───────────────────────────────────────────────────────
echo "[2/6] Connecting to $NODE_USER@$NODE_HOST..."
ssh "$NODE_USER@$NODE_HOST" bash << ENDSSH
set -e
cd "$TARGET_DIR"

echo "[3/6] Backing up postgres..."
mkdir -p ./backups
# Read the real POSTGRES_DB/POSTGRES_USER off this host's .env.prod instead of
# guessing — a hardcoded DB name here previously drifted from the actual
# POSTGRES_DB default ("tickerTap", not "tickertap") and would have silently
# backed up the wrong (nonexistent) database.
set -a; source ./.env.prod 2>/dev/null || true; set +a
_db_name="\${POSTGRES_DB:-tickerTap}"
_db_user="\${POSTGRES_USER:-postgres}"
if docker compose -f "$COMPOSE_FILE" --env-file .env.prod ps -q "$DB_SERVICE" 2>/dev/null | grep -q .; then
  docker compose -f "$COMPOSE_FILE" --env-file .env.prod exec -T "$DB_SERVICE" pg_dump -U "\$_db_user" "\$_db_name" \
    > ./backups/backup_\$(date +%Y%m%d_%H%M%S).sql && echo "Backup saved." || echo "WARNING: Backup failed, continuing."
else
  echo "WARNING: DB container not running, skipping backup."
fi

echo "[4/6] Pulling code..."
git fetch --tags && git checkout main && git pull origin main

echo "[5/6] Rebuilding containers..."
docker compose -f "$COMPOSE_FILE" --env-file .env.prod down && docker compose -f "$COMPOSE_FILE" --env-file .env.prod up -d --build

echo "[6/6] Running Alembic migrations..."
sleep 4
docker compose -f "$COMPOSE_FILE" --env-file .env.prod exec -T app alembic upgrade head
echo "Migrations done."
ENDSSH

# ── Uptime Kuma ping ─────────────────────────────────────────────────────────
if [ -n "$KUMA_PUSH_URL" ]; then
  curl -s "${KUMA_PUSH_URL}?status=up&msg=${VERSION}&ping=" > /dev/null
  echo "Kuma notified."
fi

echo ""
echo "tickerTap $VERSION deployed."
