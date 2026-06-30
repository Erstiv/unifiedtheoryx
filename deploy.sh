#!/bin/bash
#
# deploy.sh — push this local repo to the live filou deployment and restart it.
#
# Prod lives at filou:/opt/unified-theory, runs as the systemd service
# "unified-theory.service" on 127.0.0.1:8016, fronted by nginx at
# https://unifiedtheoryx.com.
#
# This script ONLY syncs code. It never touches prod's runtime state:
#   .env (secrets), *.db (the live database), topics/ (generated episodes), venv/.
# Those are excluded below, so a deploy can't wipe your data or your API keys.
#
# Usage:
#   ./deploy.sh            # sync code + restart + health check
#   ./deploy.sh --dry-run  # show exactly what WOULD change, transfer nothing
#
set -euo pipefail

REMOTE="filou"
REMOTE_DIR="/opt/unified-theory"
SERVICE="unified-theory.service"
HEALTH_URL="https://unifiedtheoryx.com/"

DRY=""
if [[ "${1:-}" == "--dry-run" ]]; then
    DRY="--dry-run"
    echo ">>> DRY RUN — no files will be transferred, service will NOT restart"
fi

cd "$(dirname "$0")"

echo ">>> Syncing code to ${REMOTE}:${REMOTE_DIR} ..."
# -rc       recurse, compare by checksum (not just timestamp)
# -i        show per-file what changed
# --chmod   force sane perms so nginx (www-data) can always read (see memory)
# --exclude protect prod runtime state + local junk
rsync -rci $DRY \
    --chmod=D755,F644 \
    --exclude='.git/' \
    --exclude='.claude/' \
    --exclude='.env' \
    --exclude='.env.*' \
    --exclude='*.db' \
    --exclude='*.db.*' \
    --exclude='topics/' \
    --exclude='venv/' \
    --exclude='__pycache__/' \
    --exclude='*.pyc' \
    --exclude='.DS_Store' \
    --exclude='deploy.sh' \
    ./ "${REMOTE}:${REMOTE_DIR}/"

if [[ -n "$DRY" ]]; then
    echo ">>> Dry run complete. Re-run without --dry-run to apply."
    exit 0
fi

echo ">>> Restarting ${SERVICE} ..."
ssh "$REMOTE" "sudo systemctl restart ${SERVICE}"
sleep 2

echo ">>> Service state:"
ssh "$REMOTE" "systemctl is-active ${SERVICE}"

echo ">>> Health check ${HEALTH_URL}"
CODE=$(curl -s -o /dev/null -w '%{http_code}' "$HEALTH_URL")
echo "    HTTP ${CODE}"
if [[ "$CODE" == "200" ]]; then
    echo ">>> Deploy OK."
else
    echo "!!! Site returned ${CODE} — check: ssh ${REMOTE} 'sudo journalctl -u ${SERVICE} -n 50'"
    exit 1
fi
