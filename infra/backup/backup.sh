#!/usr/bin/env bash
set -euo pipefail
# Daily pg_dump -> DigitalOcean Spaces
# Uses env vars: PGHOST, PGUSER, PGPASSWORD, PGDATABASE, S3_ENDPOINT, S3_BUCKET, S3_ACCESS_KEY, S3_SECRET_KEY
# Optional: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID for failure alerts

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
DUMP_FILE="/tmp/matcher_${TIMESTAMP}.dump"

echo "Starting backup at ${TIMESTAMP}"

# Create dump
pg_dump -Fc -h "${PGHOST}" -U "${PGUSER}" -d "${PGDATABASE}" > "${DUMP_FILE}"

# Upload to S3-compatible storage (DigitalOcean Spaces)
s3cmd put "${DUMP_FILE}" "s3://${S3_BUCKET}/daily/matcher_${TIMESTAMP}.dump" \
  --host="${S3_ENDPOINT}" \
  --host-bucket="${S3_BUCKET}.${S3_ENDPOINT}" \
  --access_key="${S3_ACCESS_KEY}" \
  --secret_key="${S3_SECRET_KEY}"

# Cleanup
rm -f "${DUMP_FILE}"

# Delete old backups (keep 30 days)
s3cmd ls "s3://${S3_BUCKET}/daily/" \
  --host="${S3_ENDPOINT}" \
  --host-bucket="${S3_BUCKET}.${S3_ENDPOINT}" \
  --access_key="${S3_ACCESS_KEY}" \
  --secret_key="${S3_SECRET_KEY}" | \
  while read -r line; do
    file_date=$(echo "$line" | awk '{print $1}')
    file_path=$(echo "$line" | awk '{print $4}')
    if [[ -n "$file_date" && -n "$file_path" ]]; then
      days_old=$(( ($(date +%s) - $(date -d "$file_date" +%s)) / 86400 )) 2>/dev/null || continue
      if [[ $days_old -gt 30 ]]; then
        s3cmd del "$file_path" --host="${S3_ENDPOINT}" --host-bucket="${S3_BUCKET}.${S3_ENDPOINT}" \
          --access_key="${S3_ACCESS_KEY}" --secret_key="${S3_SECRET_KEY}"
      fi
    fi
  done

echo "Backup completed successfully"
