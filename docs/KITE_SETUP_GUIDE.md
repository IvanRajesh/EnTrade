# Kite Connect Setup Guide for ExitWave

Step-by-step guide to get your Kite Connect API credentials and configure ExitWave.

---

## Step 0: Prerequisites

Before you begin, ensure you have:

- **Active Zerodha Trading Account** — You must have a Zerodha demat + trading account with F&O segment enabled.
- **2FA TOTP Enabled** — Kite Connect requires Time-based OTP (TOTP) for login. Set it up via:
  - Kite Web → Settings → Security → Enable TOTP
  - Or follow: [Zerodha TOTP Setup Guide](https://support.zerodha.com/category/trading-and-markets/general-kite/login-credentials-of-trading-platforms/articles/time-based-otp-setup)

---

## Step 1: Create a Kite Connect Developer Account

1. Go to **[https://developers.kite.trade/signup](https://developers.kite.trade/signup)**
2. Sign up with:
   - Your **email address**
   - A **password** (this is for the developer portal, separate from your Zerodha login)
3. Verify your email by clicking the confirmation link sent to your inbox.
4. Log in at **[https://developers.kite.trade/login](https://developers.kite.trade/login)**

---

## Step 2: Understand the Three App Types

When you create an app, you must choose one of three types. Here's what each means:

### A. **Connect** App — ✅ RECOMMENDED for ExitWave

| Aspect | Details |
|---|---|
| **Purpose** | Full API access — place orders, fetch positions, stream data |
| **Who uses it** | Individual traders building their own trading tools |
| **Cost** | **₹500/month** (auto-deducted from linked Zerodha account) |
| **User scope** | Only **your own** Zerodha account |
| **APIs available** | All — orders, positions, holdings, quotes, historical data, WebSocket |
| **Why for ExitWave** | We need `positions()` and `place_order()` — both require Connect |

### B. **Personal** App (Free)

| Aspect | Details |
|---|---|
| **Purpose** | Read-only access — view portfolio, stream market data |
| **Who uses it** | Developers experimenting or building dashboards |
| **Cost** | **Free** |
| **User scope** | Only your own account |
| **APIs available** | Read-only — quotes, instruments, holdings (NO order placement) |
| **Why NOT for ExitWave** | ❌ **Cannot place orders** — ExitWave needs to place exit orders |

### C. **Publisher** App

| Aspect | Details |
|---|---|
| **Purpose** | Let website visitors place orders on Kite via a button/widget |
| **Who uses it** | Financial websites, advisory platforms, charting tools |
| **Cost** | Free (but requires approval) |
| **User scope** | Multiple users (your website visitors) |
| **APIs available** | Only the Kite Publisher JS widget — no REST API access |
| **Why NOT for ExitWave** | ❌ **No API access at all** — only a JavaScript button widget |

### Verdict

> **Use "Connect" app type.** It's the only one that gives us programmatic access to place exit orders and fetch positions. Cost is ₹500/month.

---

## Step 3: Create a Connect App

1. Log in to **[https://developers.kite.trade](https://developers.kite.trade/login)**
2. Click **"Create new app"** (or similar button on the dashboard)
3. Fill in the form:

| Field | What to Enter | Explanation |
|---|---|---|
| **App Name** | `ExitWave` | Any name you like — just for identification |
| **App Type** | **Connect** | Select "Connect" from the dropdown |
| **Redirect URL** | `http://127.0.0.1:5678` | See detailed explanation below ⬇️ |
| **Postback URL** | *(leave blank)* | Optional webhook — not needed for ExitWave |
| **Description** | `Automated F&O position exit system` | Brief description of your app |

4. Click **"Create"** / **"Submit"**
5. Your app is created. You'll see:
   - **API Key** — a string like `abcdef1234ghij`
   - **API Secret** — a longer string (click "Show" to reveal)

6. **Copy both values immediately** — you'll need them in the next step.

---

## Step 4: Understanding the Redirect URL

### What is the Redirect URL?

The redirect URL is where Zerodha sends you **after you log in**. It's part of the OAuth authentication flow:

```
You click "Login" on Kite
    → You enter Zerodha credentials + TOTP on Kite's website
    → Kite verifies your identity
    → Kite redirects your browser to YOUR redirect URL
    → The redirect URL has a `request_token` appended as a query parameter
    → Your app captures this token and exchanges it for an access_token
```

### Why `http://127.0.0.1:5678`?

| Concept | Explanation |
|---|---|
| `127.0.0.1` | This is **localhost** — your own computer. The redirect stays on your machine. |
| `:5678` | This is the **port number** where ExitWave runs a tiny temporary HTTP server. |
| `http://` (not https) | Localhost doesn't need SSL. |

**When you run ExitWave with `--login`**, it:
1. Starts a lightweight HTTP server on `http://127.0.0.1:5678`
2. Opens your browser to Kite's login page
3. You log in normally
4. Kite redirects to `http://127.0.0.1:5678?request_token=XXXXX&status=success`
5. ExitWave's server catches this request, extracts the `request_token`
6. Exchanges it for an `access_token` using the Kite API
7. Shuts down the temporary server

**The redirect URL never leaves your computer.** No data is sent to any external server.

### Can I change the port?

Yes. If port 5678 is taken, you can:
1. Set a different port in Kite Developer portal (e.g., `http://127.0.0.1:9999`)
2. Run ExitWave with: `python -m exitwave --max-loss 5000 --redirect-port 9999`

> ⚠️ **CRITICAL**: The redirect URL in the Kite Developer portal **MUST exactly match** what ExitWave uses. If the portal says `http://127.0.0.1:5678`, ExitWave must use port `5678`.

---

## Step 5: Configure ExitWave with Your Credentials

1. In the project folder, copy the example environment file:

```bash
copy .env.example .env
```

2. Open `.env` in a text editor and fill in your values:

```env
# Kite Connect API Credentials (REQUIRED)
KITE_API_KEY=abcdef1234ghij          ← paste your API Key here
KITE_API_SECRET=xyz789longstring...   ← paste your API Secret here

# Access token — auto-populated after first login.
# You do NOT need to fill this manually.
KITE_ACCESS_TOKEN=
```

3. **Save the file.** The `KITE_ACCESS_TOKEN` will be filled automatically after your first login.

---

## Step 6: First Login Test

Run ExitWave with the `--login` flag to test authentication:

```bash
python -m exitwave --max-loss 5000 --login --dry-run
```

What happens:
1. ExitWave starts the redirect server on port 5678
2. Your default browser opens to: `https://kite.zerodha.com/connect/login?api_key=YOUR_KEY&v=3`
3. **Log in with your Zerodha client ID + password + TOTP**
4. Browser redirects to `http://127.0.0.1:5678?request_token=...`
5. You see: *"Login successful! You can close this tab."*
6. Back in terminal, ExitWave confirms authentication and starts monitoring

If you see `"Authenticated as: YOUR_NAME (YOUR_ID)"` — you're all set!

---

## Step 7: Daily Usage

Access tokens expire daily around **6:00 AM IST**. Each trading day:

- **First run of the day**: Use `--login` to get a fresh token
  ```bash
  python -m exitwave --max-loss 5000 --login
  ```
- **Subsequent runs same day**: Token is cached in `.env`, no login needed
  ```bash
  python -m exitwave --max-loss 5000
  ```

---

## Subscription & Billing

| Item | Cost | Billing |
|---|---|---|
| Kite Connect (Connect app) | ₹500/month | Auto-deducted from Zerodha account |
| Historical Data API | Free | Included with Connect subscription |
| Developer Account | Free | No charge for the portal account |

- Subscription activates when you create a Connect app.
- You can deactivate/delete the app anytime to stop billing.
- Check or manage subscription at [developers.kite.trade](https://developers.kite.trade)

---

## Troubleshooting

| Issue | Solution |
|---|---|
| *"The user is not enabled on the app"* | Your Zerodha client ID isn't linked to the app. Check app settings in developer portal. |
| *"Token is invalid or has expired"* | Run with `--login` to get a fresh token. Tokens expire daily at ~6 AM IST. |
| *"api_key should be minimum 6 characters"* | You pasted the wrong value. Copy the API Key (not Secret) from the developer portal. |
| Browser doesn't open | Manually visit the URL shown in the terminal. |
| *"Connection refused"* on redirect | Port 5678 may be in use. Try `--redirect-port 9999` and update the portal redirect URL. |
| *"Redirect URL mismatch"* | The URL in Kite portal must **exactly** match `http://127.0.0.1:PORT` (no trailing slash). |

---

## Security Notes

- **Never share** your `api_secret` or `access_token` with anyone.
- The `.env` file is gitignored — it won't be pushed to GitHub.
- The redirect server only binds to `127.0.0.1` (not `0.0.0.0`), so it's not accessible from the network.
- Access tokens are ephemeral (1 day validity).
