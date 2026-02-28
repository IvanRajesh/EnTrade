"""
Configuration management for ExitWave.

Loads settings from:
  1. .env file (api keys, secrets)
  2. CLI arguments (max-loss, poll-interval, etc.)
  3. Optional settings.yaml for defaults
"""

import argparse
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from dotenv import load_dotenv


@dataclass
class KiteCredentials:
    """Zerodha Kite API credentials."""
    api_key: str = ""
    api_secret: str = ""
    access_token: str = ""


@dataclass
class ExitWaveConfig:
    """Complete runtime configuration for ExitWave."""
    # Kite credentials
    credentials: KiteCredentials = field(default_factory=KiteCredentials)

    # Core trading parameters
    max_loss: float = 0.0           # Max loss threshold in ₹ (positive number)
    poll_interval: int = 10         # Seconds between position polls
    market_close: str = "15:30"     # Market close time IST (HH:MM)
    exchanges: List[str] = field(default_factory=lambda: ["NFO", "BFO"])

    # Behavior flags
    dry_run: bool = False           # If True, log but don't place exit orders
    force_login: bool = False       # Force fresh login flow
    manual_login: bool = False      # Manual login (paste request_token from another device)

    # Paths
    project_root: Path = field(default_factory=lambda: Path(__file__).parent.parent)
    log_dir: Path = field(default_factory=lambda: Path(__file__).parent.parent / "logs")

    # Auth redirect server
    redirect_port: int = 5678       # Local port for auth redirect capture


def load_env(project_root: Path) -> KiteCredentials:
    """Load Kite API credentials from .env file."""
    env_path = project_root / ".env"
    load_dotenv(dotenv_path=env_path)

    return KiteCredentials(
        api_key=os.getenv("KITE_API_KEY", ""),
        api_secret=os.getenv("KITE_API_SECRET", ""),
        access_token=os.getenv("KITE_ACCESS_TOKEN", ""),
    )


def parse_cli_args(args=None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        prog="exitwave",
        description="ExitWave — Automated F&O Position Exit System for Zerodha Kite",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m exitwave --max-loss 5000
  python -m exitwave --max-loss 10000 --poll-interval 5 --dry-run
  python -m exitwave --max-loss 5000 --login
        """,
    )

    parser.add_argument(
        "--max-loss",
        type=float,
        required=True,
        help="Maximum loss threshold in ₹ (positive number). "
             "When total F&O P&L drops below -max_loss, all positions are exited.",
    )
    parser.add_argument(
        "--poll-interval",
        type=int,
        default=10,
        help="Seconds between position polling cycles (default: 10)",
    )
    parser.add_argument(
        "--market-close",
        type=str,
        default="15:30",
        help="Market close time in IST as HH:MM (default: 15:30)",
    )
    parser.add_argument(
        "--exchanges",
        type=str,
        default="NFO,BFO",
        help="Comma-separated exchanges to monitor for F&O positions (default: NFO,BFO)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Simulate exit orders without actually placing them",
    )
    parser.add_argument(
        "--login",
        action="store_true",
        default=False,
        help="Force fresh Kite login (ignore cached access_token)",
    )
    parser.add_argument(
        "--manual-login",
        action="store_true",
        default=False,
        help="Manual login mode — login on phone/another device, paste request_token here. "
             "Use when kite.zerodha.com is blocked on your network.",
    )
    parser.add_argument(
        "--redirect-port",
        type=int,
        default=5678,
        help="Local port for Kite auth redirect capture (default: 5678)",
    )

    return parser.parse_args(args)


def build_config(args=None) -> ExitWaveConfig:
    """Build the complete ExitWave configuration from .env + CLI args."""
    cli = parse_cli_args(args)
    project_root = Path(__file__).parent.parent
    credentials = load_env(project_root)

    # Validate credentials
    if not credentials.api_key or not credentials.api_secret:
        print("ERROR: KITE_API_KEY and KITE_API_SECRET must be set in .env file.")
        print(f"  Copy .env.example to .env and fill in your credentials:")
        print(f"    {project_root / '.env.example'}")
        sys.exit(1)

    # Validate max-loss
    if cli.max_loss <= 0:
        print("ERROR: --max-loss must be a positive number (e.g., --max-loss 5000)")
        sys.exit(1)

    config = ExitWaveConfig(
        credentials=credentials,
        max_loss=cli.max_loss,
        poll_interval=cli.poll_interval,
        market_close=cli.market_close,
        exchanges=[e.strip().upper() for e in cli.exchanges.split(",")],
        dry_run=cli.dry_run,
        force_login=cli.login or cli.manual_login,
        manual_login=cli.manual_login,
        project_root=project_root,
        log_dir=project_root / "logs",
        redirect_port=cli.redirect_port,
    )

    return config
