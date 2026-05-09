#!/bin/bash
# Deploy gnss-monitor to Raspberry Pi
set -euo pipefail

PI_HOST="obs-pi-01@zenith.local"
PI_DIR="/home/obs-pi-01/gnss-monitor"
LOCAL_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "→ Syncing project files to ${PI_HOST}:${PI_DIR}"
rsync -avz --delete \
  --exclude '__pycache__' \
  --exclude '*.pyc' \
  --exclude '.DS_Store' \
  --exclude 'data/' \
  --exclude 'logs/' \
  --exclude '*.db' \
  --exclude '*.log' \
  --exclude '.env' \
  --exclude '.env.*' \
  --exclude 'rpi_setup.txt' \
  --exclude '.claude/' \
  --exclude '.git/' \
  --exclude '_bmad/' \
  --exclude 'openspec/' \
  --exclude 'epics/' \
  --exclude 'ops/' \
  --exclude 'tests/' \
  --exclude 'spec-anchor-py/' \
  "${LOCAL_DIR}/" "${PI_HOST}:${PI_DIR}/"

echo "→ Creating runtime directories"
ssh "${PI_HOST}" "mkdir -p ${PI_DIR}/data ${PI_DIR}/logs"

echo "→ Installing systemd service"
ssh "${PI_HOST}" "sudo cp ${PI_DIR}/systemd/gnss-monitor.service /etc/systemd/system/ && \
  sudo systemctl daemon-reload && \
  sudo systemctl enable gnss-monitor"

echo "→ Restarting service"
ssh "${PI_HOST}" "sudo systemctl restart gnss-monitor && sleep 2 && sudo systemctl status gnss-monitor --no-pager"

echo "✓ Deployed. Dashboard: http://$(ssh ${PI_HOST} hostname -I | awk '{print $1}'):5000"
