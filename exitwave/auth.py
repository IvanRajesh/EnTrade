"""
Kite Connect authentication module for ExitWave.

Handles the complete login flow:
  1. Check if cached access_token is still valid
  2. If not, open browser for Kite login
  3. Capture request_token via local redirect server
  4. Exchange for access_token
  5. Persist access_token to .env
"""

import os
import re
import threading
import time
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from kiteconnect import KiteConnect

from exitwave.notifier import get_logger


class _TokenCaptureHandler(BaseHTTPRequestHandler):
    """HTTP handler that captures the request_token from Kite's redirect."""

    request_token = None

    def do_GET(self):
        """Handle the GET redirect from Kite login."""
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        if "request_token" in params:
            _TokenCaptureHandler.request_token = params["request_token"][0]
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            response = """
            <html><body style="font-family: Arial, sans-serif; display: flex;
            align-items: center; justify-content: center; height: 100vh;
            background: #0d1117; color: #58a6ff;">
            <div style="text-align: center;">
                <h1>ExitWave</h1>
                <p style="color: #8b949e; font-size: 1.2em;">
                    Login successful! You can close this tab.<br>
                    ExitWave is now monitoring your positions.
                </p>
            </div>
            </body></html>
            """
            self.wfile.write(response.encode())
        else:
            self.send_response(400)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(b"<html><body><h1>Login failed. No request_token received.</h1></body></html>")

    def log_message(self, format, *args):
        """Suppress default HTTP server logging."""
        pass


def _save_access_token(project_root: Path, access_token: str):
    """Persist the access_token to the .env file."""
    env_path = project_root / ".env"

    if not env_path.exists():
        # Create .env with just the token
        with open(env_path, "w") as f:
            f.write(f"KITE_ACCESS_TOKEN={access_token}\n")
        return

    content = env_path.read_text()

    # Replace existing token or append
    if "KITE_ACCESS_TOKEN" in content:
        content = re.sub(
            r"KITE_ACCESS_TOKEN=.*",
            f"KITE_ACCESS_TOKEN={access_token}",
            content,
        )
    else:
        content += f"\nKITE_ACCESS_TOKEN={access_token}\n"

    env_path.write_text(content)


def _try_cached_token(api_key: str, access_token: str) -> KiteConnect | None:
    """
    Try to use a cached access_token. Returns KiteConnect instance if valid, None otherwise.
    """
    if not access_token:
        return None

    log = get_logger()
    log.info("Checking cached access token...")

    kite = KiteConnect(api_key=api_key)
    kite.set_access_token(access_token)

    try:
        profile = kite.profile()
        log.info(f"Authenticated as: {profile['user_name']} ({profile['user_id']})")
        return kite
    except Exception:
        log.info("Cached access token is invalid or expired.")
        return None


def _login_flow(api_key: str, api_secret: str, redirect_port: int, project_root: Path) -> KiteConnect:
    """
    Run the full Kite login flow:
      1. Start local HTTP server for redirect capture
      2. Open browser to Kite login URL
      3. Wait for request_token
      4. Exchange for access_token
    """
    log = get_logger()

    kite = KiteConnect(api_key=api_key)

    # Configure redirect URL — must match what's set in Kite Developer portal
    redirect_url = f"http://127.0.0.1:{redirect_port}"
    login_url = kite.login_url()

    log.info(f"Starting authentication server on {redirect_url}")
    log.info("Opening Kite login page in your browser...")
    log.info("")
    log.info(f"  If the browser doesn't open automatically, visit:")
    log.info(f"  {login_url}")
    log.info("")
    log.info("  IMPORTANT: Your Kite app's redirect URL must be set to:")
    log.info(f"  {redirect_url}")
    log.info("")

    # Start local server in background
    _TokenCaptureHandler.request_token = None
    server = HTTPServer(("127.0.0.1", redirect_port), _TokenCaptureHandler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    # Open browser
    webbrowser.open(login_url)

    # Wait for the request_token (timeout: 120 seconds)
    log.info("Waiting for login... (timeout: 120 seconds)")
    timeout = 120
    elapsed = 0
    while _TokenCaptureHandler.request_token is None and elapsed < timeout:
        time.sleep(1)
        elapsed += 1

    server.shutdown()

    if _TokenCaptureHandler.request_token is None:
        raise TimeoutError(
            "Login timed out. No request_token received within 120 seconds. "
            "Please ensure your Kite app redirect URL is set to "
            f"{redirect_url}"
        )

    request_token = _TokenCaptureHandler.request_token
    log.info("Request token received. Generating session...")

    # Exchange request_token for access_token
    data = kite.generate_session(request_token, api_secret=api_secret)
    access_token = data["access_token"]

    log.info(f"Session generated successfully.")
    log.info(f"Authenticated as: {data.get('user_name', 'N/A')} ({data.get('user_id', 'N/A')})")

    # Persist access_token
    _save_access_token(project_root, access_token)
    log.debug(f"Access token saved to .env")

    return kite


def _manual_login_flow(api_key: str, api_secret: str, project_root: Path) -> KiteConnect:
    """
    Manual login flow for restricted networks where kite.zerodha.com is blocked.

    User opens the login URL on their phone/personal device, completes login,
    and pastes back the request_token from the redirect URL.
    """
    log = get_logger()
    kite = KiteConnect(api_key=api_key)
    login_url = kite.login_url()

    log.info("")
    log.info("=" * 64)
    log.info("  MANUAL LOGIN MODE")
    log.info("  (Use when kite.zerodha.com is blocked on your network)")
    log.info("=" * 64)
    log.info("")
    log.info("  Step 1: Open this URL on your PHONE or personal device:")
    log.info("")
    log.info(f"  {login_url}")
    log.info("")
    log.info("  Step 2: Log in with your Zerodha credentials + TOTP")
    log.info("")
    log.info("  Step 3: After login, your browser will redirect to a URL like:")
    log.info("    http://127.0.0.1:5678?request_token=XXXXX&action=login&status=success")
    log.info("    (The page won't load — that's fine!)")
    log.info("")
    log.info("  Step 4: Copy the 'request_token' value from that URL")
    log.info("    and paste it below.")
    log.info("")

    user_input = input("  Paste request_token (or full redirect URL): ").strip()

    # Extract request_token from full URL or direct paste
    if "request_token=" in user_input:
        parsed = parse_qs(urlparse(user_input).query)
        if "request_token" in parsed:
            request_token = parsed["request_token"][0]
        else:
            raise ValueError("Could not extract request_token from the URL.")
    else:
        request_token = user_input

    if not request_token:
        raise ValueError("No request_token provided.")

    log.info(f"Request token received ({request_token[:8]}...). Generating session...")

    # Exchange request_token for access_token (this calls api.kite.trade which works)
    data = kite.generate_session(request_token, api_secret=api_secret)
    access_token = data["access_token"]

    log.info(f"Session generated successfully.")
    log.info(f"Authenticated as: {data.get('user_name', 'N/A')} ({data.get('user_id', 'N/A')})")

    _save_access_token(project_root, access_token)
    log.debug("Access token saved to .env")

    return kite


def authenticate(api_key: str, api_secret: str, access_token: str,
                 force_login: bool, redirect_port: int,
                 project_root: Path, manual_login: bool = False) -> KiteConnect:
    """
    Authenticate with Kite Connect.

    Tries cached token first; falls back to full login flow.

    Args:
        api_key: Kite API key.
        api_secret: Kite API secret.
        access_token: Cached access token (may be empty/expired).
        force_login: Skip cached token, force fresh login.
        redirect_port: Port for local auth redirect server.
        project_root: Project root for .env persistence.

    Returns:
        Authenticated KiteConnect instance.
    """
    log = get_logger()

    # Try cached token unless force_login
    if not force_login:
        kite = _try_cached_token(api_key, access_token)
        if kite is not None:
            return kite

    # Manual login flow (for restricted networks)
    if manual_login:
        log.info("Starting manual login flow...")
        return _manual_login_flow(api_key, api_secret, project_root)

    # Full browser login flow
    log.info("Starting Kite login flow...")
    return _login_flow(api_key, api_secret, redirect_port, project_root)
