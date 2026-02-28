#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────
# ExitWave — Daily Token Refresh Script
# ─────────────────────────────────────────────────────────
# Kite access tokens expire daily (~6 AM IST). This script
# runs the manual login flow to get a fresh token, then
# restarts the ExitWave service.
#
# Usage (interactive — requires user input for request_token):
#   sudo -u exitwave /opt/exitwave/deploy/refresh-token.sh
#
# Cron example (runs at 9:00 AM IST every weekday):
#   0 9 * * 1-5 /opt/exitwave/deploy/refresh-token.sh
#   (Note: requires manual input, so cron won't work unattended.
#    See the ENGINEERING_SPEC for automated TOTP solutions.)
# ─────────────────────────────────────────────────────────

set -euo pipefail

INSTALL_DIR="/opt/exitwave"

echo "═══════════════════════════════════════════════════════"
echo "  ExitWave — Token Refresh"
echo "═══════════════════════════════════════════════════════"
echo ""

cd "$INSTALL_DIR"

# Run manual login in dry-run mode (just to get the token)
"$INSTALL_DIR/venv/bin/python" -m exitwave --max-loss 99999 --manual-login --dry-run

echo ""
echo "Token refreshed. Restarting ExitWave service..."

# Restart the service if running as root or with sudo
if [ "$EUID" -eq 0 ]; then
    systemctl restart exitwave
    echo "Service restarted."
    systemctl status exitwave --no-pager
else
    echo "Not running as root. Restart manually:"
    echo "  sudo systemctl restart exitwave"
fi
