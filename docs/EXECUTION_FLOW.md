# ExitWave — Detailed Execution Flow Guide

A line-by-line walkthrough of the entire ExitWave system, from the moment you type the command to the final exit. This document is written for someone starting fresh who wants to understand exactly what the code does at every step.

---

## Table of Contents

1. [How to Launch ExitWave](#1-how-to-launch-exitwave)
2. [Phase 1: Entry Point — `__main__.py`](#2-phase-1-entry-point)
3. [Phase 2: Configuration — `config.py`](#3-phase-2-configuration)
4. [Phase 3: Logging Setup — `notifier.py`](#4-phase-3-logging-setup)
5. [Phase 4: Authentication — `auth.py`](#5-phase-4-authentication)
6. [Phase 5: Position Monitoring — `monitor.py`](#6-phase-5-position-monitoring)
7. [Phase 6: Position Fetching & P&L — `positions.py`](#7-phase-6-position-fetching--pl)
8. [Phase 7: Exit Execution — `executor.py`](#8-phase-7-exit-execution)
9. [Phase 8: Shutdown & Summary](#9-phase-8-shutdown--summary)
10. [Complete Call Graph](#10-complete-call-graph)
11. [Data Flow Diagram](#11-data-flow-diagram)
12. [Scenario Walkthroughs](#12-scenario-walkthroughs)

---

## 1. How to Launch ExitWave

```powershell
.\venv\Scripts\python.exe -m exitwave --max-loss 5000 --dry-run
```

When Python sees `-m exitwave`, it:
1. Finds the `exitwave/` package directory
2. Loads `exitwave/__init__.py` — sets `__version__ = "1.0.0"` and `__app_name__ = "ExitWave"`
3. Executes `exitwave/__main__.py` — this is the entry point

---

## 2. Phase 1: Entry Point

**File:** `exitwave/__main__.py`

```
python -m exitwave --max-loss 5000 --dry-run
       │
       ▼
__main__.py → main()
```

### What happens (line by line):

**Line 50** — `config = build_config()`
- Calls `config.py` to load `.env` file and parse CLI arguments
- Returns a fully populated `ExitWaveConfig` dataclass
- **If credentials are missing → prints error and exits with code 1**
- **If `--max-loss` is ≤ 0 → prints error and exits with code 1**

**Line 53** — `logger = setup_logging(config.log_dir, dry_run=config.dry_run)`
- Sets up dual logging: colored console output + daily log file
- Creates `logs/` directory if it doesn't exist
- Log file: `logs/exitwave_2026-02-28.log` (or `logs/exitwave_dryrun_2026-02-28.log`)

**Line 55** — `_print_banner()`
- Prints the ASCII art "EXIT WAVE" banner to console

**Lines 57-59** — Startup log messages
- Logs version info
- If `--dry-run` is set, logs a yellow warning: "DRY-RUN MODE"

**Lines 62-77** — `kite = authenticate(...)`
- Calls `auth.py` to get an authenticated `KiteConnect` instance
- On failure → logs error and exits with code 1
- See [Phase 4: Authentication](#5-phase-4-authentication) for the full auth flow

**Line 80** — `monitor = PositionMonitor(kite=kite, config=config)`
- Creates the monitor object with the authenticated Kite client and config
- Does NOT start monitoring yet — just initializes state

**Lines 82-88** — Signal handlers
- Registers `SIGINT` (Ctrl+C) and `SIGTERM` handlers
- Both call `monitor.stop()` which sets a threading Event to cleanly stop the loop

**Line 90** — `monitor.start()`
- Launches the background monitoring thread
- The monitor loop begins executing in parallel (see Phase 5)

**Lines 92-95** — Info message
- Prints: "ExitWave is now monitoring your F&O positions. Press Ctrl+C to stop."

**Lines 97-102** — `monitor.wait()`
- **Main thread blocks here** — waits for the background monitor thread to finish
- The monitor thread finishes when:
  - Market close time is reached (default 15:30 IST), OR
  - Exit orders are triggered (threshold breached), OR
  - User presses Ctrl+C, OR
  - An unrecoverable error occurs (e.g., token expired)

**Lines 104-110** — Final status
- Checks `monitor.has_exited` to determine the outcome
- Logs whether positions were exited or left to expire
- Exits with code 0 (success in both cases)

---

## 3. Phase 2: Configuration

**File:** `exitwave/config.py`

### Data Structures

**`KiteCredentials`** (dataclass):
```
┌─────────────────────────────────┐
│ api_key:      str  (from .env)  │
│ api_secret:   str  (from .env)  │
│ access_token: str  (from .env)  │
└─────────────────────────────────┘
```

**`ExitWaveConfig`** (dataclass):
```
┌───────────────────────────────────────────────────────┐
│ credentials:   KiteCredentials                        │
│ max_loss:      float  (from --max-loss CLI arg)       │
│ poll_interval: int    (default 10 seconds)            │
│ market_close:  str    (default "15:30")               │
│ exchanges:     List   (default ["NFO", "BFO"])        │
│ dry_run:       bool   (from --dry-run flag)           │
│ force_login:   bool   (from --login or --manual-login)│
│ manual_login:  bool   (from --manual-login flag)      │
│ project_root:  Path   (auto-detected)                 │
│ log_dir:       Path   (project_root / "logs")         │
│ redirect_port: int    (default 5678)                  │
└───────────────────────────────────────────────────────┘
```

### `build_config()` flow:

```
build_config()
  │
  ├─ parse_cli_args()
  │    └─ argparse parses sys.argv
  │       Required: --max-loss
  │       Optional: --poll-interval, --market-close, --exchanges,
  │                 --dry-run, --login, --manual-login, --redirect-port
  │
  ├─ load_env(project_root)
  │    └─ dotenv reads .env file
  │       Reads: KITE_API_KEY, KITE_API_SECRET, KITE_ACCESS_TOKEN
  │       Returns: KiteCredentials
  │
  ├─ VALIDATE: api_key and api_secret must be non-empty
  │    └─ If empty → print error, sys.exit(1)
  │
  ├─ VALIDATE: max_loss must be > 0
  │    └─ If ≤ 0 → print error, sys.exit(1)
  │
  └─ Return ExitWaveConfig with all values populated
```

### CLI Arguments Reference

| Argument | Type | Required | Default | Example |
|---|---|---|---|---|
| `--max-loss` | float | **Yes** | — | `5000` |
| `--poll-interval` | int | No | `10` | `5` |
| `--market-close` | str | No | `"15:30"` | `"15:20"` |
| `--exchanges` | str | No | `"NFO,BFO"` | `"NFO"` |
| `--dry-run` | flag | No | `False` | — |
| `--login` | flag | No | `False` | — |
| `--manual-login` | flag | No | `False` | — |
| `--redirect-port` | int | No | `5678` | `9999` |

---

## 4. Phase 3: Logging Setup

**File:** `exitwave/notifier.py`

### `setup_logging()` flow:

```
setup_logging(log_dir, dry_run)
  │
  ├─ Create logs/ directory (mkdir -p)
  │
  ├─ Get or create logger named "exitwave"
  │    └─ Level: DEBUG (captures everything)
  │
  ├─ Console Handler (StreamHandler → stdout)
  │    ├─ Level: INFO (hides DEBUG from console)
  │    └─ Formatter: ConsoleFormatter
  │         ├─ Timestamps in IST (Asia/Kolkata)
  │         └─ Colors:
  │              DEBUG    → Grey
  │              INFO     → White
  │              WARNING  → Yellow
  │              ERROR    → Red
  │              CRITICAL → Bold Red
  │
  └─ File Handler (logs/exitwave_YYYY-MM-DD.log)
       ├─ Level: DEBUG (captures everything)
       └─ Formatter: ISTFormatter
            └─ Format: [2026-02-28 14:30:00 IST] [INFO ] message
```

### Log output example:

**Console** (colored):
```
[2026-02-28 14:30:00 IST] [INFO ] ExitWave v1.0.0 starting...
[2026-02-28 14:30:05 IST] [WARNING] P&L: Rs.-3,500 | Threshold: Rs.-5,000 (70%)
[2026-02-28 14:30:15 IST] [CRITICAL] THRESHOLD BREACHED! P&L: Rs.-5,200
```

**File** (`logs/exitwave_2026-02-28.log`) — same format, no colors, includes DEBUG lines.

### Using the logger anywhere:

Any module calls `get_logger()` → returns the same `"exitwave"` logger instance.

---

## 5. Phase 4: Authentication

**File:** `exitwave/auth.py`

### Three authentication paths:

```
authenticate()
  │
  ├─ PATH A: Cached Token (default, fastest)
  │    │
  │    ├─ Check: Is force_login False AND access_token non-empty?
  │    ├─ _try_cached_token(api_key, access_token)
  │    │    ├─ Create KiteConnect(api_key)
  │    │    ├─ kite.set_access_token(access_token)
  │    │    ├─ Call kite.profile()    ←── API call to api.kite.trade
  │    │    │    ├─ SUCCESS → Log "Authenticated as: Name (ID)"
  │    │    │    │            Return kite instance ✅
  │    │    │    └─ FAIL    → Log "token invalid/expired"
  │    │    │                 Fall through to Path B or C
  │    │    └─ Return KiteConnect or None
  │    │
  │    └─ If token valid → DONE (no browser needed)
  │
  ├─ PATH B: Manual Login (--manual-login flag)
  │    │
  │    ├─ _manual_login_flow(api_key, api_secret, project_root)
  │    │    ├─ Create KiteConnect(api_key)
  │    │    ├─ Get login_url from kite.login_url()
  │    │    ├─ Print instructions to console:
  │    │    │    "Open this URL on your PHONE: https://kite.zerodha.com/connect/login?..."
  │    │    ├─ Wait for user input: request_token or full redirect URL
  │    │    ├─ Parse request_token from input
  │    │    │    ├─ If input contains "request_token=" → extract from URL query params
  │    │    │    └─ Otherwise → use raw input as the token
  │    │    ├─ kite.generate_session(request_token, api_secret)  ←── API call
  │    │    │    └─ Returns: { "access_token": "...", "user_name": "...", "user_id": "..." }
  │    │    ├─ _save_access_token(project_root, access_token)
  │    │    │    └─ Updates KITE_ACCESS_TOKEN=... in .env file
  │    │    └─ Return authenticated kite instance ✅
  │    │
  │    └─ Use when: Corporate firewall blocks kite.zerodha.com
  │
  └─ PATH C: Browser Login (--login flag)
       │
       ├─ _login_flow(api_key, api_secret, redirect_port, project_root)
       │    ├─ Create KiteConnect(api_key)
       │    ├─ Start HTTPServer on 127.0.0.1:5678
       │    │    └─ Handler: _TokenCaptureHandler
       │    │         └─ Captures request_token from GET query params
       │    ├─ Open browser to kite.login_url()
       │    │    └─ https://kite.zerodha.com/connect/login?api_key=XXX&v=3
       │    ├─ Wait up to 120 seconds for redirect
       │    │    └─ Kite redirects browser → http://127.0.0.1:5678?request_token=YYY
       │    │    └─ _TokenCaptureHandler.do_GET() captures the token
       │    │    └─ Shows "Login successful!" HTML page in browser
       │    ├─ server.shutdown()
       │    ├─ If no token received → raise TimeoutError
       │    ├─ kite.generate_session(request_token, api_secret)  ←── API call
       │    ├─ _save_access_token() → updates .env
       │    └─ Return authenticated kite instance ✅
       │
       └─ Use when: Network is unrestricted, browser available
```

### Token lifecycle:

```
┌──────────────────────────────────────────────────────────┐
│                    Token Timeline                         │
├──────────────────────────────────────────────────────────┤
│                                                          │
│  ~6:00 AM ──── access_token generated ───── valid ─────  │
│                                                          │
│  9:15 AM ──── Market opens ──── ExitWave starts ───────  │
│                        ↑                                 │
│                        │ kite.profile() → OK             │
│                        │ (cached token works)            │
│                                                          │
│  3:30 PM ──── Market closes ── ExitWave stops ─────────  │
│                                                          │
│  ~6:00 AM ──── token EXPIRES ── next day ──────────────  │
│                        ↑                                 │
│                        │ kite.profile() → FAIL           │
│                        │ (need fresh login)              │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

---

## 6. Phase 5: Position Monitoring

**File:** `exitwave/monitor.py`

This is the **core engine** — a background thread that runs the poll-check-exit loop.

### `PositionMonitor` initialization:

```
PositionMonitor.__init__(kite, config)
  │
  ├─ Store kite client and config
  ├─ Parse market_close "15:30" → _close_hour=15, _close_minute=30
  ├─ Create threading.Event (_stop_event) for clean shutdown
  ├─ Initialize state:
  │    _exited = False       (no exit triggered yet)
  │    _exit_results = []    (no order results yet)
  │    _poll_count = 0       (polls completed)
  │    _last_pnl = None      (last observed P&L)
  │    _peak_loss = 0.0      (worst P&L seen)
  └─ Logger reference
```

### `monitor.start()` → launches background thread:

```
monitor.start()
  │
  ├─ Clear stop event and reset counters
  ├─ Create Thread(target=_monitor_loop, name="ExitWave-Monitor", daemon=True)
  ├─ thread.start()  ←── Background thread begins
  └─ Log "Position monitor started."

Main thread returns immediately. Monitor runs in parallel.
```

### `_monitor_loop()` — the heart of ExitWave:

```
_monitor_loop()   [runs in background thread]
  │
  ├─ Log monitor configuration summary
  │    (Max Loss, Poll Interval, Market Close, Exchanges, Dry Run)
  │
  └─ LOOP (while _stop_event is NOT set):
       │
       ├─ CHECK: Is market still open?
       │    │
       │    ├─ Get current time in IST
       │    ├─ Compare with market_close (15:30)
       │    ├─ If now >= 15:30 IST:
       │    │    └─ Log "Market close time reached. Stopping."
       │    │       BREAK out of loop
       │    └─ If before 15:30 → continue
       │
       ├─ POLL: _poll_positions()
       │    │
       │    ├─ Fetch open F&O positions from Kite API
       │    │    └─ See Phase 6 for details
       │    │
       │    ├─ If NO positions:
       │    │    └─ Log "No open F&O positions" (every ~60s)
       │    │       RETURN (wait for next poll)
       │    │
       │    ├─ Calculate total P&L across all positions
       │    │    └─ total_pnl = sum of each position's .pnl field
       │    │
       │    ├─ Track peak loss (worst P&L observed)
       │    │
       │    ├─ Calculate loss_ratio = |total_pnl| / max_loss
       │    │
       │    ├─ LOG based on severity:
       │    │    ├─ loss_ratio >= 1.0 (100%+)
       │    │    │    └─ CRITICAL: "THRESHOLD BREACHED!"
       │    │    │       → _trigger_exit(positions, total_pnl)
       │    │    │       → RETURN (loop will break on _exited flag)
       │    │    │
       │    │    ├─ loss_ratio >= 0.8 (80-99%)
       │    │    │    └─ WARNING: "APPROACHING THRESHOLD"
       │    │    │
       │    │    ├─ loss_ratio >= 0.5 (50-79%)
       │    │    │    └─ WARNING: P&L status with percentage
       │    │    │
       │    │    └─ loss_ratio < 0.5 (0-49%)
       │    │         └─ INFO: Normal P&L status
       │    │
       │    └─ Every 30 polls (~5 min): log detailed position breakdown
       │
       └─ WAIT: _stop_event.wait(timeout=poll_interval)
            └─ Sleeps for 10 seconds (default)
               OR wakes immediately if stop() is called

  NOTE: After an exit event, the monitor enters a 30-second
  cooldown, then CONTINUES monitoring for new positions.
  The loop only ends at market close (15:30 IST) or Ctrl+C.

  After loop ends:
  ├─ Log "Monitor loop ended."
  └─ _print_session_summary()
```

### Poll timing visualization:

```
  09:30:00  09:30:10  09:30:20  ...  10:45:10  ...  10:45:40  ...  15:30:00
     │         │         │              │              │              │
     ▼         ▼         ▼              ▼              ▼              ▼
   POLL 1   POLL 2   POLL 3  ...    POLL N         RESUME    ...  MARKET CLOSE
    P&L:     P&L:     P&L:         P&L:           Monitoring      → STOP
   -1200    -1800    -2500        -5200           continues
    24%      36%      50%        104% ← BREACH!  ← watching for
    INFO     INFO    WARN        CRIT → EXIT        new positions
                                   │
                                   ▼
                               _trigger_exit()
                               Place MARKET orders
                               Verify orders
                               30s cooldown
                                   │
                                   ▼
                               RESUME MONITORING
                               (new positions may appear)
                               Runs until 15:30 IST
```

---

## 7. Phase 6: Position Fetching & P&L

**File:** `exitwave/positions.py`

### `get_open_fno_positions()` — called every poll cycle:

```
get_open_fno_positions(kite, exchanges=["NFO", "BFO"])
  │
  ├─ fetch_positions(kite)
  │    └─ kite.positions()  ←── Kite API call
  │         Returns: {
  │           "net": [                           ← We use this
  │             {
  │               "tradingsymbol": "NIFTY2530622500CE",
  │               "exchange": "NFO",
  │               "instrument_token": 12345678,
  │               "product": "NRML",
  │               "quantity": -50,              ← Negative = SHORT
  │               "average_price": 120.50,
  │               "last_price": 145.75,
  │               "pnl": -1262.50,              ← Loss on this leg
  │               "m2m": -1262.50,
  │               "buy_quantity": 0,
  │               "sell_quantity": 50,
  │               "buy_price": 0,
  │               "sell_price": 120.50
  │             },
  │             { ... more positions ... }
  │           ],
  │           "day": [ ... ]                     ← Ignored by ExitWave
  │         }
  │
  ├─ parse_fno_positions(raw, exchanges)
  │    │
  │    ├─ Iterate through raw["net"]
  │    ├─ FILTER: Only keep positions where exchange ∈ ["NFO", "BFO"]
  │    │    └─ Skips: NSE, BSE, MCX (equity, commodity positions)
  │    ├─ Convert each dict → FnOPosition dataclass
  │    └─ Return List[FnOPosition]
  │
  └─ FILTER: Only keep positions where quantity ≠ 0
       └─ quantity == 0 means position is already closed/flat
       Return: List[FnOPosition] (open positions only)
```

### `FnOPosition` dataclass:

```
┌─────────────────────────────────────────────┐
│ FnOPosition                                 │
├─────────────────────────────────────────────┤
│ tradingsymbol:  "NIFTY2530622500CE"         │
│ exchange:       "NFO"                       │
│ instrument_token: 12345678                  │
│ product:        "NRML"                      │
│ quantity:       -50   (SHORT 50 lots)       │
│ average_price:  120.50                      │
│ last_price:     145.75                      │
│ pnl:            -1262.50                    │
│ m2m:            -1262.50                    │
│ buy_quantity:   0                           │
│ sell_quantity:  50                           │
│ buy_price:      0.0                         │
│ sell_price:     120.50                      │
├─────────────────────────────────────────────┤
│ .is_open  → True (quantity ≠ 0)             │
│ .side     → "SHORT" (quantity < 0)          │
│ .__str__  → "NIFTY...CE | SHORT 50 |       │
│              Avg: 120.50 | LTP: 145.75 |   │
│              P&L: -1262.50"                 │
└─────────────────────────────────────────────┘
```

### `calculate_total_pnl()`:

```
positions = [
  NIFTY2530622500CE  pnl = -1262.50
  NIFTY2530622300PE  pnl = +800.00
  NIFTY2530622600CE  pnl = -4537.50
]

total_pnl = sum(p.pnl for p in positions)
          = (-1262.50) + (800.00) + (-4537.50)
          = -5000.00   ← This triggers exit if max_loss = 5000
```

---

## 8. Phase 7: Exit Execution

**File:** `exitwave/executor.py`

### `_trigger_exit()` in monitor.py calls `exit_all_positions()`:

```
_trigger_exit(positions, total_pnl)
  │
  ├─ Log CRITICAL: "Initiating emergency exit for N position(s)"
  ├─ Log each position being exited
  │
  ├─ exit_all_positions(kite, positions, dry_run)
  │    │
  │    ├─ For EACH position:
  │    │    │
  │    │    └─ place_exit_order(kite, position, dry_run)
  │    │         │
  │    │         ├─ Determine exit direction:
  │    │         │    ├─ quantity > 0 (LONG)  → SELL
  │    │         │    └─ quantity < 0 (SHORT) → BUY
  │    │         │
  │    │         ├─ exit_quantity = abs(quantity)
  │    │         │
  │    │         ├─ IF dry_run:
  │    │         │    └─ Log "[DRY-RUN] EXIT ORDER: SELL 50 NIFTY...CE @ MARKET"
  │    │         │       Return success (no actual order)
  │    │         │
  │    │         └─ REAL ORDER (up to 3 attempts):
  │    │              │
  │    │              └─ kite.place_order(        ←── Kite API call
  │    │                   variety   = "regular"
  │    │                   exchange  = "NFO"
  │    │                   tradingsymbol = "NIFTY2530622500CE"
  │    │                   transaction_type = "BUY"   (to close SHORT)
  │    │                   quantity  = 50
  │    │                   product   = "NRML"
  │    │                   order_type = "MARKET"
  │    │                   validity  = "DAY"
  │    │                   tag       = "ExitWave"
  │    │                 )
  │    │                   │
  │    │                   ├─ SUCCESS → Returns order_id
  │    │                   │    Log: "EXIT ORDER: BUY 50 NIFTY...CE @ MARKET → Order ID: 12345"
  │    │                   │
  │    │                   └─ FAIL → Retry after 1 second
  │    │                        Attempt 2 → Retry after 1 second
  │    │                        Attempt 3 → Log ERROR, return failure
  │    │
  │    ├─ Count: successful orders, failed orders
  │    ├─ If all succeeded → Log "All N exit order(s) placed successfully"
  │    └─ If any failed → Log ERROR with details of each failure
  │
  ├─ _exit_results = results
  ├─ _exited = True   ←── This breaks the monitor loop
  │
  └─ IF NOT dry_run:
       │
       └─ verify_exit_orders(kite, results)
            │
            ├─ Wait 2 seconds for orders to process
            │
            └─ For EACH successful order:
                 │
                 └─ kite.order_history(order_id)  ←── Kite API call
                      │
                      ├─ Get latest status from order history
                      │
                      ├─ "COMPLETE"  → Log "CONFIRMED: NIFTY...CE — Order 12345 COMPLETE"
                      ├─ "REJECTED"  → Log ERROR with rejection reason
                      └─ Other       → Log WARNING "PENDING: status: OPEN"
```

### Exit order logic per position:

```
┌─────────────────────────────────────────────────────────────┐
│              EXIT ORDER DIRECTION LOGIC                      │
├──────────────────────┬──────────────────────────────────────┤
│ Position Side        │ Exit Order                           │
├──────────────────────┼──────────────────────────────────────┤
│ LONG  (qty = +50)    │ SELL 50 @ MARKET                     │
│ SHORT (qty = -50)    │ BUY  50 @ MARKET                     │
│ FLAT  (qty = 0)      │ Skip (nothing to exit)               │
└──────────────────────┴──────────────────────────────────────┘

All exit orders are MARKET orders → immediate execution at best available price.
Product type (NRML/MIS) is preserved from the original position.
Tag "ExitWave" is attached for easy identification in Kite order book.
```

---

## 9. Phase 8: Shutdown & Summary

After the monitor loop ends (for any reason), `_print_session_summary()` runs:

```
════════════════════════════════════════════════════════════
  ExitWave Session Summary
════════════════════════════════════════════════════════════
  Total polls         : 324
  Last P&L            : Rs.-5,200.00
  Peak loss           : Rs.-5,200.00
  Threshold           : Rs.-5,000.00
  Exit triggered      : YES
  Exit orders placed  : 3 succeeded, 0 failed
════════════════════════════════════════════════════════════
```

### Three possible outcomes:

| Outcome | Cause | `has_exited` | Exit Code |
|---|---|---|---|
| **Exit triggered** | P&L breached threshold | `True` | 0 |
| **Market closed** | Time >= 15:30 IST | `False` | 0 |
| **Manual stop** | User pressed Ctrl+C | `False` | 0 |
| **Auth error** | Token expired mid-session | `False` | 0 |

---

## 10. Complete Call Graph

```
python -m exitwave --max-loss 5000
│
└─ __main__.py → main()
    │
    ├─ config.py → build_config()
    │   ├─ parse_cli_args()         ← argparse
    │   └─ load_env()               ← python-dotenv reads .env
    │
    ├─ notifier.py → setup_logging()
    │   └─ Creates console + file handlers with IST timestamps
    │
    ├─ auth.py → authenticate()
    │   ├─ _try_cached_token()      ← kite.profile()         [API]
    │   ├─ _manual_login_flow()     ← kite.generate_session() [API]
    │   └─ _login_flow()            ← HTTPServer + browser + kite.generate_session()
    │
    ├─ monitor.py → PositionMonitor(kite, config)
    │   └─ .start() → spawns background thread
    │       │
    │       └─ _monitor_loop()  [BACKGROUND THREAD]
    │           │
    │           └─ LOOP every 10s:
    │               │
    │               ├─ _is_market_open()
    │               │
    │               ├─ _poll_positions()
    │               │   ├─ positions.py → get_open_fno_positions()
    │               │   │   ├─ fetch_positions()    ← kite.positions()  [API]
    │               │   │   └─ parse_fno_positions() + filter open
    │               │   │
    │               │   ├─ positions.py → calculate_total_pnl()
    │               │   │
    │               │   └─ IF threshold breached:
    │               │       └─ _trigger_exit()
    │               │           ├─ executor.py → exit_all_positions()
    │               │           │   └─ place_exit_order()  × N positions
    │               │           │       └─ kite.place_order()  [API] (3 retries)
    │               │           │
    │               │           └─ executor.py → verify_exit_orders()
    │               │               └─ kite.order_history()  [API] × N orders
    │               │
    │               └─ _stop_event.wait(10s)
    │
    ├─ monitor.wait()  [MAIN THREAD BLOCKS HERE]
    │
    └─ Print final status and exit
```

---

## 11. Data Flow Diagram

```
┌─────────┐     ┌──────────┐     ┌─────────────┐
│  .env   │────→│ config.py│────→│ ExitWaveConfig│
│  file   │     │          │     │  dataclass    │
└─────────┘     └──────────┘     └──────┬────────┘
                                        │
┌─────────┐     ┌──────────┐            │
│  CLI    │────→│ argparse │────────────┘
│  args   │     │          │
└─────────┘     └──────────┘


┌──────────────┐     ┌──────────────┐     ┌───────────────┐
│ Kite Login   │────→│   auth.py    │────→│ KiteConnect   │
│ (browser/    │     │              │     │ (authenticated│
│  manual)     │     └──────────────┘     │  instance)    │
└──────────────┘                          └──────┬────────┘
                                                 │
                                                 ▼
                    ┌─────────────────────────────────────┐
                    │         monitor.py                    │
                    │    _monitor_loop() [BG THREAD]       │
                    │                                      │
                    │  ┌─────────────────────────────────┐ │
                    │  │  EVERY 10 SECONDS:              │ │
                    │  │                                 │ │
                    │  │  kite.positions()               │ │
                    │  │       │                         │ │
                    │  │       ▼                         │ │
                    │  │  positions.py                   │ │
                    │  │  ├─ Filter NFO/BFO              │ │
                    │  │  ├─ Filter qty ≠ 0              │ │
                    │  │  └─ Sum P&L                     │ │
                    │  │       │                         │ │
                    │  │       ▼                         │ │
                    │  │  total_pnl <= -max_loss ?       │ │
                    │  │  ├─ NO  → log status, continue  │ │
                    │  │  └─ YES → executor.py           │ │
                    │  │           ├─ place_order() × N  │ │
                    │  │           └─ verify orders      │ │
                    │  └─────────────────────────────────┘ │
                    └─────────────────────────────────────┘
                                   │
                                   ▼
                    ┌──────────────────────────────┐
                    │  logs/exitwave_YYYY-MM-DD.log │
                    │  + colored console output     │
                    └──────────────────────────────┘
```

---

## 12. Scenario Walkthroughs

### Scenario A: Normal Day — No Threshold Breach

```
09:25 AM  → Run: python -m exitwave --max-loss 5000
09:25 AM  → Config loaded, logger set up
09:25 AM  → Auth: cached token valid ✅
09:25 AM  → Monitor starts (poll every 10s)
09:25 AM  → "No open F&O positions" (you haven't placed trades yet)
09:30 AM  → You manually place NIFTY option trades on Kite app
09:30:10  → Poll: 2 positions found, P&L: Rs.-200 (4%)  → INFO
09:35:00  → Poll: P&L: Rs.-1,500 (30%)                  → INFO
10:15:00  → Poll: P&L: Rs.-2,800 (56%)                  → WARNING
11:30:00  → Poll: P&L: Rs.+500                          → INFO (in profit!)
02:45:00  → Poll: P&L: Rs.-1,200 (24%)                  → INFO
03:30:00  → "Market close time reached. Stopping."
03:30:00  → Session Summary: 2160 polls, no exit triggered
03:30:00  → "ExitWave completed — no exit triggered. Positions left to expire."
```

### Scenario B: Threshold Breached — Exit + Continue Monitoring

```
09:30 AM  → Monitor running, --max-loss 5000
10:00 AM  → Poll: P&L: Rs.-1,000 (20%)                  → INFO
10:30 AM  → Poll: P&L: Rs.-3,200 (64%)                  → WARNING
10:45 AM  → Poll: P&L: Rs.-4,100 (82%)                  → WARNING "APPROACHING THRESHOLD"
10:45:10  → Poll: P&L: Rs.-5,200 (104%)                 → CRITICAL "THRESHOLD BREACHED!"
10:45:10  → _trigger_exit() #1 called
10:45:10  → Exit order 1: BUY 50 NIFTY2530622500CE @ MARKET → Order ID: 12345
10:45:10  → Exit order 2: SELL 50 NIFTY2530622300PE @ MARKET → Order ID: 12346
10:45:12  → Verify: Order 12345 → COMPLETE ✅
10:45:12  → Verify: Order 12346 → COMPLETE ✅
10:45:12  → "Exit #1 complete. Resuming monitoring in 30s..."
10:45:42  → Cooldown ends, polling resumes
10:46:00  → "No open F&O positions found. Continuing to monitor..."
           ... monitor keeps running, watching for new positions ...
03:30:00  → "Market close time reached. Stopping."
03:30:00  → Session Summary: 1 exit event, 2 orders placed
```

### Scenario B2: Multiple Exits in One Day

```
10:45:10  → Exit #1 — closed initial positions (loss breached threshold)
10:45:42  → Cooldown ends, resume monitoring
11:30:00  → You enter new positions on Kite app
12:15:00  → Poll: new positions P&L: Rs.-5,500 (110%)  → CRITICAL
12:15:00  → _trigger_exit() #2 called
12:15:00  → Exit order 3: SELL 25 NIFTY2530623000CE @ MARKET
12:15:02  → Verify ✅
12:15:32  → Cooldown ends, resume monitoring
03:30:00  → Session Summary: 2 exit events, 3 total orders
```

### Scenario C: Dry Run

```
Same as Scenario B, but with --dry-run flag:
10:45:10  → [DRY-RUN] EXIT ORDER: BUY 50 NIFTY2530622500CE @ MARKET
10:45:10  → [DRY-RUN] EXIT ORDER: SELL 50 NIFTY2530622300PE @ MARKET
10:45:10  → [DRY-RUN] Skipping order verification.
10:45:10  → "Exit #1 complete. Resuming monitoring in 30s..."
           (No real orders placed — monitor continues until 15:30)
```

### Scenario D: Token Expiry Mid-Session

```
09:30 AM  → Monitor running, auth OK
06:00 AM  → (next day) Token expires
06:00:10  → Poll: kite.positions() throws TokenException
06:00:10  → "Authentication error — access token may have expired."
06:00:10  → "Please restart ExitWave with --login flag."
06:00:10  → Monitor stops
```

---

## Kite API Calls Summary

| When | API Call | Purpose | Module |
|---|---|---|---|
| Startup (auth) | `kite.profile()` | Validate cached token | `auth.py:105` |
| Login | `kite.generate_session()` | Exchange request_token → access_token | `auth.py:169` or `auth.py:231` |
| Every poll (~10s) | `kite.positions()` | Fetch all positions | `positions.py:67` |
| On threshold breach | `kite.place_order()` | Place MARKET exit order | `executor.py:86` |
| After exit orders | `kite.order_history()` | Verify order execution | `executor.py:192` |

---

## File Responsibility Matrix

| File | Responsibility | Key Functions/Classes |
|---|---|---|
| `__init__.py` | Package metadata | `__version__`, `__app_name__` |
| `__main__.py` | CLI entry point, orchestration | `main()` |
| `config.py` | .env loading, CLI parsing, validation | `build_config()`, `ExitWaveConfig` |
| `notifier.py` | Dual logging (console color + file) in IST | `setup_logging()`, `get_logger()` |
| `auth.py` | Kite OAuth login (browser, manual, cached) | `authenticate()` |
| `positions.py` | Position fetching, filtering, P&L math | `get_open_fno_positions()`, `FnOPosition` |
| `executor.py` | Exit order placement with retries | `exit_all_positions()`, `verify_exit_orders()` |
| `monitor.py` | Background poll loop, threshold logic | `PositionMonitor` class |
