#!/usr/bin/env sh
# Back up both FirstPR databases (platform and catalogue) to compressed dumps.
#
#   scripts/backup.sh                      # Compose on this machine, into ./backups
#   DATABASE_URL=postgres://... scripts/backup.sh   # any reachable Postgres (Render)
#
# Keeps the newest $KEEP days (default 14). Run it from cron once a day, and copy
# the backups folder off the server. Restore steps are in docs/deploy.md.
set -eu

OUT="${OUT:-backups}"
KEEP="${KEEP:-14}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
COMPOSE="${COMPOSE:-docker compose -f infra/compose/compose.prod.yaml}"
mkdir -p "$OUT"

for db in firstpr firstpr_catalogue; do
  file="$OUT/$db-$STAMP.dump"
  if [ -n "${DATABASE_URL:-}" ]; then
    # Same server, other database name.
    url="$(printf '%s' "$DATABASE_URL" | sed -E "s#/[^/?]+(\?|$)#/$db\1#")"
    pg_dump --format=custom --no-owner "$url" > "$file"
  else
    $COMPOSE exec -T postgres pg_dump --format=custom --no-owner -U firstpr "$db" > "$file"
  fi
  echo "wrote $file ($(wc -c < "$file") bytes)"
done

find "$OUT" -name '*.dump' -mtime +"$KEEP" -delete
