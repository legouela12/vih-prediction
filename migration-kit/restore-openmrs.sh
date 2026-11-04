#!/usr/bin/env bash
set -euo pipefail

KIT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$KIT_DIR"
DB_BACKUP="$KIT_DIR/backup/openmrs.sql.gz"
DATA_BACKUP="$KIT_DIR/backup/openmrs-data.tar.gz"

compose() {
  if docker compose version >/dev/null 2>&1; then
    docker compose -f compose.yaml "$@"
  elif command -v docker-compose >/dev/null 2>&1; then
    docker-compose -f compose.yaml "$@"
  else
    printf 'Docker Compose est requis (greffon `docker compose` ou commande `docker-compose`).\n' >&2
    return 127
  fi
}

if [[ ! -s "$DB_BACKUP" || ! -s "$DATA_BACKUP" ]]; then
  printf 'Sauvegardes manquantes dans %s/backup.\n' "$KIT_DIR" >&2
  exit 1
fi

gzip -t "$DB_BACKUP"
tar -tzf "$DATA_BACKUP" >/dev/null

compose up -d db
ready=false
for _ in $(seq 1 60); do
  if compose exec -T db sh -ec 'healthcheck.sh --connect --innodb_initialized' >/dev/null 2>&1; then
    ready=true
    break
  fi
  sleep 2
done
if [[ "$ready" != true ]]; then
  printf 'MariaDB ne devient pas disponible. Consultez les journaux Compose du service db.\n' >&2
  exit 1
fi

table_count="$(compose exec -T db sh -ec '
  credentials=$(mktemp)
  trap "rm -f \"$credentials\"" EXIT
  printf "[client]\nuser=root\npassword=%s\n" "$MYSQL_ROOT_PASSWORD" > "$credentials"
  chmod 600 "$credentials"
  mariadb --defaults-extra-file="$credentials" --batch --skip-column-names \
    -e "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = '\''openmrs'\''"
')"
if [[ "$table_count" != "0" ]]; then
  printf 'La base de destination contient déjà des tables OpenMRS; restauration annulée.\n' >&2
  exit 1
fi

gzip -dc "$DB_BACKUP" | compose exec -T db sh -ec '
  credentials=$(mktemp)
  trap "rm -f \"$credentials\"" EXIT
  printf "[client]\nuser=root\npassword=%s\n" "$MYSQL_ROOT_PASSWORD" > "$credentials"
  chmod 600 "$credentials"
  mariadb --defaults-extra-file="$credentials" openmrs
'

# Restore files before the OpenMRS backend is started. Use the pinned MariaDB
# image as a tar helper because the OpenMRS backend image has no tar utility.
docker volume create vih-openmrs-data >/dev/null
docker run --rm --volume vih-openmrs-data:/openmrs/data --entrypoint sh \
  mariadb@sha256:d769e37960821dfdcf096954f6e7ac89f747e116c1bba98e48edd265dfc7deae \
  -ec '
  if find /openmrs/data -mindepth 1 -print -quit | grep -q .; then
    echo "Le volume openmrs-data n’est pas vide; restauration des fichiers annulée." >&2
    exit 1
  fi
  tar -C /openmrs/data -xzf -
' < "$DATA_BACKUP"

compose up -d
printf 'Restauration terminée. OpenMRS : http://127.0.0.1:%s/openmrs\n' "${OPENMRS_PORT:-8080}"
