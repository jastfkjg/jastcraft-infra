#!/usr/bin/env bash
set -euo pipefail
umask 077
case "${BACKUP_CLOUD:?Set BACKUP_CLOUD}" in
    aws) command -v aws >/dev/null; [[ "${BACKUP_DESTINATION:-}" == s3://* ]] ;;
    aliyun) command -v ossutil >/dev/null; [[ "${BACKUP_DESTINATION:-}" == oss://* ]] ;;
    *) echo 'BACKUP_CLOUD must be aws or aliyun' >&2; exit 1 ;;
esac
service=${BACKUP_SERVICE:-shadowtable}
case "$service" in
    shadowtable) database=/opt/shadowtable/data/shadowtable.sqlite ;;
    inkmind) database=/opt/inkmind/data/inkmind.db ;;
    *) echo 'Unsupported backup service' >&2; exit 1 ;;
esac
exec 9>"/opt/$service/deploy.lock"
flock -w 120 9
snapshot=$(python3 /usr/local/lib/jastcraft/backup-sqlite.py "$database" "/opt/$service/backups" --prefix "$service")
case "$BACKUP_CLOUD" in
    aws) aws s3 cp "$snapshot" "${BACKUP_DESTINATION%/}/$(basename "$snapshot")" --only-show-errors ;;
    aliyun) ossutil cp "$snapshot" "${BACKUP_DESTINATION%/}/$(basename "$snapshot")" ;;
esac
# Retain 14 days locally only after the remote upload succeeds.
find "/opt/$service/backups" -type f -name "$service-*.sqlite" -mtime +14 -delete
