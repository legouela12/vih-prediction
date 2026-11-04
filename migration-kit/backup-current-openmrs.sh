#!/usr/bin/env bash
set -euo pipefail

KIT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_DIR="$KIT_DIR/backup"
DB_CONTAINER="${OPENMRS_DB_CONTAINER:-e_db_1}"
BACKEND_CONTAINER="${OPENMRS_BACKEND_CONTAINER:-e_backend_1}"
DATA_VOLUME="${OPENMRS_DATA_VOLUME:-e_openmrs-data}"
ARCHIVE_IMAGE="mariadb@sha256:d769e37960821dfdcf096954f6e7ac89f747e116c1bba98e48edd265dfc7deae"

for container in "$DB_CONTAINER" "$BACKEND_CONTAINER"; do
  if [[ "$(docker inspect -f '{{.State.Running}}' "$container" 2>/dev/null || true)" != "true" ]]; then
    printf 'Conteneur absent ou arrêté : %s\n' "$container" >&2
    exit 1
  fi
done

umask 077
mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"
db_tmp="$BACKUP_DIR/openmrs.sql.gz.tmp"
data_tmp="$BACKUP_DIR/openmrs-data.tar.gz.tmp"
trap 'rm -f "$db_tmp" "$data_tmp"' EXIT

# Transactional InnoDB dump; credentials stay inside the database container.
docker exec "$DB_CONTAINER" sh -ec '
  credentials=$(mktemp)
  trap "rm -f \"$credentials\"" EXIT
  printf "[client]\nuser=root\npassword=%s\n" "$MYSQL_ROOT_PASSWORD" > "$credentials"
  chmod 600 "$credentials"
  mariadb-dump --defaults-extra-file="$credentials" --single-transaction --quick \
    --routines --triggers --events --hex-blob --default-character-set=utf8mb4 openmrs
' | gzip -9 > "$db_tmp"

# Preserve OpenMRS modules, configuration, indexes and files, including person images.
docker run --rm --volume "$DATA_VOLUME:/openmrs/data:ro" --entrypoint sh "$ARCHIVE_IMAGE" \
  -ec 'tar -C /openmrs/data -czf - .' > "$data_tmp"

gzip -t "$db_tmp"
tar -tzf "$data_tmp" >/dev/null
mv "$db_tmp" "$BACKUP_DIR/openmrs.sql.gz"
mv "$data_tmp" "$BACKUP_DIR/openmrs-data.tar.gz"
chmod 600 "$BACKUP_DIR/openmrs.sql.gz" "$BACKUP_DIR/openmrs-data.tar.gz"
trap - EXIT

printf 'Sauvegarde créée dans %s (accès restreint, non suivie par Git).\n' "$BACKUP_DIR"
sha256sum "$BACKUP_DIR/openmrs.sql.gz" "$BACKUP_DIR/openmrs-data.tar.gz"
