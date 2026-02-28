# ExitWave — Linux Deployment Guide

Run ExitWave as a background systemd service on Linux. It starts before market open, monitors positions all day, exits when thresholds are breached, and stops at market close.

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Quick Install](#2-quick-install)
3. [Manual Install](#3-manual-install)
4. [Daily Token Refresh](#4-daily-token-refresh)
5. [Service Management](#5-service-management)
6. [Customizing the Service](#6-customizing-the-service)
7. [Logs & Monitoring](#7-logs--monitoring)
8. [Security Hardening](#8-security-hardening)
9. [Troubleshooting](#9-troubleshooting)
10. [OS Compatibility Notes](#10-os-compatibility-notes)

---

## 1. Prerequisites

| Requirement | Details |
|---|---|
| **OS** | Ubuntu 20.04+, Debian 11+, RHEL 8+, or any systemd-based Linux |
| **Python** | 3.10 or newer |
| **Network** | Outbound HTTPS to `api.kite.trade` (port 443) |
| **Kite Connect** | Active subscription with API key and secret |

### Install Python (if needed)

```bash
# Ubuntu/Debian
sudo apt update && sudo apt install python3 python3-venv python3-pip

# RHEL/CentOS/Fedora
sudo dnf install python3 python3-pip

# Verify
python3 --version   # Must be 3.10+
```

---

## 2. Quick Install

```bash
# Clone or copy the project
cd /path/to/exitwave-source

# Run the installer
chmod +x deploy/install.sh
sudo ./deploy/install.sh
```

The installer will:
- Create a dedicated `exitwave` system user (no login shell)
- Copy files to `/opt/exitwave`
- Create a Python virtual environment and install dependencies
- Install the systemd service unit

After install, follow the on-screen instructions to configure credentials and start the service.

---

## 3. Manual Install

If you prefer to set things up manually:

### 3.1 Create system user

```bash
sudo useradd --system --no-create-home --shell /usr/sbin/nologin exitwave
```

### 3.2 Set up the application

```bash
# Create install directory
sudo mkdir -p /opt/exitwave/logs
sudo cp -r exitwave/ /opt/exitwave/
sudo cp requirements.txt /opt/exitwave/
sudo cp .env.example /opt/exitwave/.env

# Create virtual environment
sudo python3 -m venv /opt/exitwave/venv
sudo /opt/exitwave/venv/bin/pip install -r /opt/exitwave/requirements.txt

# Set ownership
sudo chown -R exitwave:exitwave /opt/exitwave
sudo chmod 600 /opt/exitwave/.env
```

### 3.3 Configure credentials

```bash
sudo -u exitwave nano /opt/exitwave/.env
```

Set `KITE_API_KEY` and `KITE_API_SECRET`.

### 3.4 First-time login (get access token)

```bash
cd /opt/exitwave
sudo -u exitwave /opt/exitwave/venv/bin/python -m exitwave \
  --max-loss 5000 --manual-login --dry-run
```

This will print a URL — open it on your phone, log in, and paste the `request_token` back.

### 3.5 Install systemd service

```bash
sudo cp deploy/exitwave.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable exitwave
sudo systemctl start exitwave
```

---

## 4. Daily Token Refresh

Kite access tokens expire daily around 6:00 AM IST. The service will detect this and stop with an auth error. You need to refresh the token each trading morning.

### Option A: Manual refresh (simplest)

```bash
# Run interactively each morning before market opens
cd /opt/exitwave
sudo -u exitwave /opt/exitwave/venv/bin/python -m exitwave \
  --max-loss 5000 --manual-login --dry-run

# Then restart the service
sudo systemctl restart exitwave
```

### Option B: Use the refresh script

```bash
sudo -u exitwave /opt/exitwave/deploy/refresh-token.sh
```

### Option C: SSH from phone (advanced)

Use an SSH client on your phone (e.g., Termius, JuiceSSH) to:
1. SSH into your Linux server
2. Run the refresh script
3. Paste the request_token from Kite login

### Token lifecycle

```
06:00 AM  ── Previous token expires
09:00 AM  ── You run manual-login, get fresh token
09:00 AM  ── Service restarts with new token
09:15 AM  ── Market opens, monitoring begins
03:30 PM  ── Market closes, service stops cleanly
           ── systemd Restart=on-failure does NOT restart (clean exit)
```

> **Note:** Full automation of daily login requires TOTP automation, which
> involves storing your Zerodha password and TOTP secret — a security
> tradeoff. See future enhancements in the engineering spec.

---

## 5. Service Management

```bash
# Start the service
sudo systemctl start exitwave

# Stop the service
sudo systemctl stop exitwave

# Restart (e.g., after token refresh)
sudo systemctl restart exitwave

# Check status
sudo systemctl status exitwave

# Enable auto-start on boot
sudo systemctl enable exitwave

# Disable auto-start
sudo systemctl disable exitwave
```

---

## 6. Customizing the Service

### Change the max-loss threshold

Edit the service file:

```bash
sudo nano /etc/systemd/system/exitwave.service
```

Find the `ExecStart` line and change `--max-loss`:

```ini
ExecStart=/opt/exitwave/venv/bin/python -m exitwave --max-loss 10000
```

Apply changes:

```bash
sudo systemctl daemon-reload
sudo systemctl restart exitwave
```

### Add more CLI flags

```ini
# Example: custom poll interval, specific exchanges
ExecStart=/opt/exitwave/venv/bin/python -m exitwave --max-loss 5000 --poll-interval 5 --exchanges NFO

# Example: dry-run mode for testing
ExecStart=/opt/exitwave/venv/bin/python -m exitwave --max-loss 5000 --dry-run
```

### Override with a drop-in file (preserves original)

```bash
sudo systemctl edit exitwave
```

This opens an editor. Add:

```ini
[Service]
ExecStart=
ExecStart=/opt/exitwave/venv/bin/python -m exitwave --max-loss 10000
```

---

## 7. Logs & Monitoring

### journald (systemd logs)

```bash
# Follow live logs
journalctl -u exitwave -f

# Today's logs
journalctl -u exitwave --since today

# Last 100 lines
journalctl -u exitwave -n 100

# Errors only
journalctl -u exitwave -p err
```

### Application log files

```bash
# Daily log files in /opt/exitwave/logs/
ls -la /opt/exitwave/logs/
cat /opt/exitwave/logs/exitwave_2026-02-28.log

# Follow the latest log file
tail -f /opt/exitwave/logs/exitwave_$(date +%Y-%m-%d).log
```

### Quick health check

```bash
# Is the service running?
systemctl is-active exitwave

# Uptime and memory usage
systemctl status exitwave --no-pager

# Process details
ps aux | grep exitwave
```

---

## 8. Security Hardening

The systemd service unit includes several security measures:

| Directive | Purpose |
|---|---|
| `User=exitwave` | Runs as dedicated non-root user |
| `NoNewPrivileges=true` | Cannot escalate privileges |
| `ProtectSystem=strict` | Filesystem is read-only except allowed paths |
| `ProtectHome=read-only` | Cannot write to /home |
| `ReadWritePaths=...` | Only logs/ and .env are writable |
| `PrivateTmp=true` | Isolated /tmp directory |
| `MemoryMax=256M` | Memory limit to prevent runaway |

### Credential protection

```bash
# .env is readable only by the exitwave user
sudo chmod 600 /opt/exitwave/.env
sudo chown exitwave:exitwave /opt/exitwave/.env

# Verify
ls -la /opt/exitwave/.env
# -rw------- 1 exitwave exitwave 256 Feb 28 19:00 /opt/exitwave/.env
```

---

## 9. Troubleshooting

### Service won't start

```bash
# Check detailed error
journalctl -u exitwave -n 50 --no-pager

# Common causes:
# 1. Missing .env or credentials
# 2. Python venv not created
# 3. Dependencies not installed
# 4. Permission issues
```

### "Authentication error — token expired"

The access token expired. Refresh it:

```bash
cd /opt/exitwave
sudo -u exitwave /opt/exitwave/venv/bin/python -m exitwave \
  --max-loss 5000 --manual-login --dry-run
sudo systemctl restart exitwave
```

### Service restarts unexpectedly

The service has `Restart=on-failure`. It will restart if ExitWave crashes (non-zero exit), but NOT after a clean market-close shutdown (exit code 0).

If you see repeated restarts:

```bash
# Check exit status
systemctl show exitwave -p ExecMainStatus
journalctl -u exitwave --since "5 minutes ago"
```

### Network issues

```bash
# Test connectivity to Kite API
curl -sI https://api.kite.trade
# Should return HTTP 200

# If behind a proxy, set in the service file:
# Environment=HTTPS_PROXY=http://proxy:port
```

---

## 10. OS Compatibility Notes

ExitWave is written in pure Python with no OS-specific dependencies. Here's what differs per platform:

### What's already cross-platform

| Component | Notes |
|---|---|
| **pathlib.Path** | All file paths use `pathlib` — works on Windows/Linux/macOS |
| **ANSI colors** | Auto-disabled when stdout is not a TTY (e.g., journald) |
| **ANSI on Windows** | Explicitly enabled via Win32 API (`SetConsoleMode`) |
| **Signal handling** | `SIGTERM` registered only on Linux/macOS (`os.name != "nt"`) |
| **HTTP server** | `http.server` stdlib — works everywhere |
| **Thread model** | `threading` stdlib — works everywhere |

### Platform-specific behavior

| Feature | Windows | Linux/macOS |
|---|---|---|
| **Run as service** | Not supported (run in terminal) | systemd service |
| **Ctrl+C handling** | `SIGINT` only | `SIGINT` + `SIGTERM` |
| **Console colors** | Win32 API enablement | Native ANSI support |
| **Log file path** | `logs\exitwave_...log` | `logs/exitwave_...log` |
| **Python invocation** | `.\venv\Scripts\python.exe -m exitwave` | `./venv/bin/python -m exitwave` |
| **Token refresh** | Manual (run `--manual-login`) | Script or manual |

### Running on macOS

ExitWave works on macOS as-is. For background running, use `launchd` instead of systemd:

```bash
# Simple foreground run
python -m exitwave --max-loss 5000

# Background with nohup
nohup python -m exitwave --max-loss 5000 &> logs/exitwave.log &
```

---

## Directory Structure on Linux

```
/opt/exitwave/
├── .env                    # Credentials (chmod 600)
├── requirements.txt
├── exitwave/               # Python package
│   ├── __init__.py
│   ├── __main__.py
│   ├── config.py
│   ├── auth.py
│   ├── monitor.py
│   ├── executor.py
│   ├── positions.py
│   └── notifier.py
├── deploy/
│   ├── exitwave.service    # systemd unit (also in /etc/systemd/system/)
│   ├── install.sh
│   └── refresh-token.sh
├── logs/                   # Daily log files
│   ├── exitwave_2026-02-28.log
│   └── exitwave_2026-03-01.log
└── venv/                   # Python virtual environment
```
