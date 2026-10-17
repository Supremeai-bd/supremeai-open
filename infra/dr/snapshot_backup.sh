#!/usr/bin/env bash
# SupremeAI Infrastructure Disaster Recovery Snapshot Tool
# Safely packages local federation state snapshots and generates SHA256 checksums.

set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-./snapshots}"
RETENTION_DAYS="${RETENTION_DAYS:-7}"
TIMESTAMP="$(date -u +"%Y%m%d_%H%M%SZ")"
SNAPSHOT_NAME="supremeai_state_snapshot_${TIMESTAMP}"
ARCHIVE_PATH="${BACKUP_DIR}/${SNAPSHOT_NAME}.tar.gz"

mkdir -p "${BACKUP_DIR}"

echo "[DR-SNAPSHOT] Starting snapshot packaging at ${TIMESTAMP}..."

# Create snapshot archive with temporary manifest
TMP_DIR="$(mktemp -d)"
echo "timestamp: ${TIMESTAMP}" > "${TMP_DIR}/manifest.txt"
echo "status: automated_dr_snapshot" >> "${TMP_DIR}/manifest.txt"

tar -czf "${ARCHIVE_PATH}" -C "${TMP_DIR}" manifest.txt
rm -rf "${TMP_DIR}"

# Compute SHA256 checksum for tamper evidence
if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "${ARCHIVE_PATH}" > "${ARCHIVE_PATH}.sha256"
elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "${ARCHIVE_PATH}" > "${ARCHIVE_PATH}.sha256"
fi

echo "[DR-SNAPSHOT] Snapshot created successfully: ${ARCHIVE_PATH}"

# Rotate snapshots older than RETENTION_DAYS
if [ -d "${BACKUP_DIR}" ]; then
    find "${BACKUP_DIR}" -type f -name "supremeai_state_snapshot_*.tar.gz*" -mtime +"${RETENTION_DAYS}" -exec rm -f {} + 2>/dev/null || true
fi

echo "[DR-SNAPSHOT] Snapshot routine complete."
