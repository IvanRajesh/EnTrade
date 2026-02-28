# ExitWave

**Automated F&O Position Exit System for Zerodha Kite**

> *Ride the trade. ExitWave catches the fall.*

ExitWave monitors your open F&O positions on Zerodha and automatically exits all positions when your aggregate unrealized loss breaches a user-defined threshold. You place orders manually via Kite — ExitWave watches your back.

---

## How It Works

```
You place F&O orders manually on Kite
        ↓
ExitWave polls your open positions every N seconds
        ↓
Computes total unrealized P&L across all F&O positions
        ↓
If total loss > your max-loss threshold → EXIT ALL positions
        ↓
After exit, continues monitoring for new positions until market close (15:30 IST)
```

## Prerequisites

### 1. Zerodha Account
- Active Zerodha trading + demat account
- 2FA TOTP enabled ([setup guide](https://support.zerodha.com/category/trading-and-markets/general-kite/login-credentials-of-trading-platforms/articles/time-based-otp-setup))

### 2. Kite Connect Developer App (₹500/month)
- Sign up at [developers.kite.trade](https://developers.kite.trade)
- Create a **Connect** app (not Personal or Publisher)
- Note your **API Key** and **API Secret**
- Set **Redirect URL** to: `http://127.0.0.1:5678`
- See **[docs/KITE_SETUP_GUIDE.md](docs/KITE_SETUP_GUIDE.md)** for detailed step-by-step instructions

> **Note:** Kite Connect API access requires a paid "Connect" app subscription (₹500/month). The free "Personal" app is read-only and cannot place orders.

### 3. Python 3.10+
- Download from [python.org](https://www.python.org/downloads/)

---

## Quick Start

### 1. Clone & Install

```bash
git clone https://github.com/IvanRajesh/EnTrade.git
cd EnTrade

# Create virtual environment
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Linux/Mac

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Credentials

```bash
copy .env.example .env       # Windows
# cp .env.example .env       # Linux/Mac
```

Edit `.env` and fill in your Kite API credentials:

```env
KITE_API_KEY=your_api_key_here
KITE_API_SECRET=your_api_secret_here
```

### 3. Run ExitWave

```bash
# Monitor positions, exit if loss exceeds ₹5000
python -m exitwave --max-loss 5000

# First run / re-login (opens browser for Kite login)
python -m exitwave --max-loss 5000 --login

# Manual login (for corporate networks where kite.zerodha.com is blocked)
python -m exitwave --max-loss 5000 --manual-login

# Dry run (simulate without placing real exit orders)
python -m exitwave --max-loss 5000 --dry-run

# Custom poll interval (every 5 seconds)
python -m exitwave --max-loss 10000 --poll-interval 5
```

---

## CLI Reference

```
python -m exitwave --max-loss <amount> [options]
```

| Argument | Type | Default | Description |
|---|---|---|---|
| `--max-loss` | float | **Required** | Max loss threshold in ₹ (positive number) |
| `--poll-interval` | int | 10 | Seconds between position polls |
| `--market-close` | str | `15:30` | Market close time IST (HH:MM) |
| `--exchanges` | str | `NFO,BFO` | Exchanges to monitor (comma-separated) |
| `--dry-run` | flag | off | Simulate exits without placing orders |
| `--login` | flag | off | Force fresh Kite login |
| `--manual-login` | flag | off | Paste request_token from another device |
| `--redirect-port` | int | 5678 | Port for auth redirect server |

---

## Authentication Flow

ExitWave uses Kite Connect's OAuth-like login:

1. **First run**: ExitWave opens your browser to the Kite login page
2. **You log in** with your Zerodha credentials + TOTP
3. Kite redirects to `http://127.0.0.1:5678` — ExitWave captures the token
4. The `access_token` is saved to `.env` for reuse
5. **Subsequent runs** (same day): uses cached token — no browser needed

> Access tokens expire daily (~6 AM IST). You'll need to re-login each trading day using `--login`.

### Manual Login (Corporate Networks)

If `kite.zerodha.com` is blocked on your network, use `--manual-login`:
1. ExitWave prints a login URL
2. Open it on your phone/personal device and log in
3. Copy the `request_token` from the redirect URL
4. Paste it back into ExitWave

---

## Project Structure

```
EnTrade/
├── exitwave/                # Main package
│   ├── __init__.py          # Package metadata
│   ├── __main__.py          # CLI entry point & orchestration
│   ├── config.py            # Configuration (.env + CLI args)
│   ├── auth.py              # Kite login flow & token management
│   ├── monitor.py           # Background position polling thread
│   ├── executor.py          # Exit order placement & verification
│   ├── positions.py         # Position parsing & P&L calculation
│   └── notifier.py          # Logging (console + file, IST timezone)
├── deploy/                  # Linux systemd deployment
│   ├── exitwave.service     # systemd unit file
│   ├── install.sh           # Automated installer
│   └── refresh-token.sh     # Daily token refresh helper
├── docs/                    # Documentation
│   ├── EXECUTION_FLOW.md    # Detailed code execution flow guide
│   ├── KITE_SETUP_GUIDE.md  # Kite Connect setup instructions
│   └── LINUX_DEPLOYMENT.md  # Linux systemd deployment guide
├── logs/                    # Runtime logs (auto-created, gitignored)
├── .env.example             # Credentials template
├── .gitignore
├── requirements.txt
└── README.md
```

---

## Linux Deployment

ExitWave can run as a systemd service on Linux. See **[docs/LINUX_DEPLOYMENT.md](docs/LINUX_DEPLOYMENT.md)** for full instructions.

```bash
# Quick install
sudo ./deploy/install.sh

# Manage the service
sudo systemctl start exitwave
sudo systemctl status exitwave
journalctl -u exitwave -f
```

---

## Kite APIs Used

| API Method | Purpose |
|---|---|
| `kite.login_url()` | Generate Kite login URL |
| `kite.generate_session()` | Exchange request_token for access_token |
| `kite.profile()` | Verify authentication |
| `kite.positions()` | Fetch all open positions (core polling) |
| `kite.place_order()` | Place MARKET exit orders |
| `kite.order_history()` | Verify exit order completion |

---

## Example Session

```
╔══════════════════════════════════════════════════════╗
║   ExitWave — Automated F&O Position Exit System      ║
╚══════════════════════════════════════════════════════╝

[09:30:15 IST] [INFO ] ExitWave v1.0.0 starting...
[09:30:15 IST] [INFO ] Authenticated as: RAJESH (AB1234)
[09:30:15 IST] [INFO ] Max Loss Threshold : Rs.5,000.00
[09:30:15 IST] [INFO ] Poll Interval      : 10s
[09:30:25 IST] [INFO ] P&L: Rs.-800.00 | Threshold: Rs.-5,000.00 | Positions: 2
[09:31:05 IST] [WARN ] P&L: Rs.-3,500.00 | Threshold: Rs.-5,000.00 (70%) | Positions: 2
[09:31:15 IST] [WARN ] P&L: Rs.-4,200.00 | (84%) | APPROACHING THRESHOLD
[09:31:25 IST] [CRIT ] THRESHOLD BREACHED! P&L: Rs.-5,100.00
[09:31:25 IST] [CRIT ] Initiating emergency exit #1 for 2 position(s).
[09:31:26 IST] [INFO ] EXIT ORDER: SELL 50 NIFTY2540322000CE @ MARKET
[09:31:26 IST] [INFO ] EXIT ORDER: BUY 50 NIFTY2540322000PE @ MARKET
[09:31:28 IST] [INFO ] All 2 exit order(s) placed successfully.
[09:31:28 IST] [INFO ] Exit #1 complete. Resuming monitoring in 30s...
[09:32:00 IST] [INFO ] No open F&O positions found. Continuing to monitor...
        ... continues monitoring until 15:30 IST ...
[15:30:00 IST] [INFO ] Market close time reached. Stopping.
```

---

## Risk Disclaimer

> **ExitWave is a tool, not financial advice.** F&O trading involves significant risk of loss. ExitWave makes a best-effort attempt to exit positions when thresholds are breached, but cannot guarantee execution due to market conditions, API failures, or network issues. Always monitor your positions independently. Use at your own risk.

---

## License

MIT
