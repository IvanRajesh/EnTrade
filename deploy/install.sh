#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────
# ExitWave — Linux Installation & Service Setup Script
# ─────────────────────────────────────────────────────────
# Usage:
#   chmod +x deploy/install.sh
#   sudo ./deploy/install.sh
#
# What this script does:
#   1. Creates a dedicated 'exitwave' system user
#   2. Copies project files to /opt/exitwave
#   3. Creates a Python virtual environment and installs dependencies
#   4. Installs the systemd service unit
#   5. Prompts for initial configuration
# ─────────────────────────────────────────────────────────

set -euo pipefail

INSTALL_DIR="/opt/exitwave"
SERVICE_NAME="exitwave"
SERVICE_USER="exitwave"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; }

# ─── Pre-flight checks ──────────────────────────────────

if [ "$EUID" -ne 0 ]; then
    error "This script must be run as root (sudo)."
    exit 1
fi

# Check Python 3.10+
if ! command -v python3 &> /dev/null; then
    error "python3 not found. Install Python 3.10+ first."
    error "  Ubuntu/Debian: sudo apt install python3 python3-venv python3-pip"
    error "  RHEL/CentOS:   sudo dnf install python3 python3-pip"
    exit 1
fi

PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PYTHON_MAJOR=$(echo "$PYTHON_VERSION" | cut -d. -f1)
PYTHON_MINOR=$(echo "$PYTHON_VERSION" | cut -d. -f2)

if [ "$PYTHON_MAJOR" -lt 3 ] || ([ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 10 ]); then
    error "Python 3.10+ required. Found: python3 $PYTHON_VERSION"
    exit 1
fi

info "Python $PYTHON_VERSION found."

# ─── Create system user ─────────────────────────────────

if id "$SERVICE_USER" &>/dev/null; then
    info "User '$SERVICE_USER' already exists."
else
    info "Creating system user '$SERVICE_USER'..."
    useradd --system --no-create-home --shell /usr/sbin/nologin "$SERVICE_USER"
    info "User '$SERVICE_USER' created."
fi

# ─── Copy project files ─────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

info "Installing ExitWave to $INSTALL_DIR..."
mkdir -p "$INSTALL_DIR"

# Copy source files
cp -r "$SCRIPT_DIR/exitwave" "$INSTALL_DIR/"
cp "$SCRIPT_DIR/requirements.txt" "$INSTALL_DIR/"

# Copy .env.example if .env doesn't exist
if [ ! -f "$INSTALL_DIR/.env" ]; then
    if [ -f "$SCRIPT_DIR/.env.example" ]; then
        cp "$SCRIPT_DIR/.env.example" "$INSTALL_DIR/.env"
        warn ".env copied from .env.example — you MUST edit it with your API credentials."
    fi
else
    info ".env already exists — preserving existing configuration."
fi

# Create logs directory
mkdir -p "$INSTALL_DIR/logs"

# ─── Create virtual environment ─────────────────────────

if [ ! -d "$INSTALL_DIR/venv" ]; then
    info "Creating Python virtual environment..."
    python3 -m venv "$INSTALL_DIR/venv"
else
    info "Virtual environment already exists."
fi

info "Installing Python dependencies..."
"$INSTALL_DIR/venv/bin/pip" install --quiet --upgrade pip
"$INSTALL_DIR/venv/bin/pip" install --quiet -r "$INSTALL_DIR/requirements.txt"
info "Dependencies installed."

# ─── Set permissions ─────────────────────────────────────

chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR"
chmod 600 "$INSTALL_DIR/.env"  # Protect credentials
info "Permissions set (credentials file restricted to $SERVICE_USER)."

# ─── Install systemd service ────────────────────────────

info "Installing systemd service..."
cp "$SCRIPT_DIR/deploy/exitwave.service" /etc/systemd/system/exitwave.service
systemctl daemon-reload
info "Service installed."

# ─── Initial token setup ────────────────────────────────

echo ""
echo "═══════════════════════════════════════════════════════"
echo "  ExitWave Installation Complete!"
echo "═══════════════════════════════════════════════════════"
echo ""
echo "  Install directory : $INSTALL_DIR"
echo "  Service name      : $SERVICE_NAME"
echo "  Service user      : $SERVICE_USER"
echo "  Python            : $INSTALL_DIR/venv/bin/python"
echo ""
echo "  Next steps:"
echo ""
echo "  1. Edit credentials:"
echo "     sudo -u $SERVICE_USER nano $INSTALL_DIR/.env"
echo "     (Set KITE_API_KEY and KITE_API_SECRET)"
echo ""
echo "  2. First-time login (get access token):"
echo "     sudo -u $SERVICE_USER $INSTALL_DIR/venv/bin/python -m exitwave \\"
echo "       --max-loss 5000 --manual-login --dry-run"
echo "     (Run from $INSTALL_DIR)"
echo ""
echo "  3. Edit service max-loss threshold:"
echo "     sudo nano /etc/systemd/system/exitwave.service"
echo "     (Change --max-loss value in ExecStart line)"
echo ""
echo "  4. Enable and start the service:"
echo "     sudo systemctl enable exitwave"
echo "     sudo systemctl start exitwave"
echo ""
echo "  5. Check status and logs:"
echo "     sudo systemctl status exitwave"
echo "     journalctl -u exitwave -f"
echo ""
echo "═══════════════════════════════════════════════════════"
