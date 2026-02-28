"""
ExitWave — CLI entry point.

Usage:
  python -m exitwave --max-loss 5000
  python -m exitwave --max-loss 10000 --poll-interval 5 --dry-run
  python -m exitwave --max-loss 5000 --login
"""

import os
import signal
import sys

from exitwave import __version__, __app_name__
from exitwave.config import build_config
from exitwave.notifier import setup_logging, get_logger
from exitwave.auth import authenticate
from exitwave.monitor import PositionMonitor


def _print_banner():
    """Print the ExitWave startup banner."""
    banner = rf"""
    ╔══════════════════════════════════════════════════════╗
    ║                                                      ║
    ║   ███████╗██╗  ██╗██╗████████╗                       ║
    ║   ██╔════╝╚██╗██╔╝██║╚══██╔══╝                       ║
    ║   █████╗   ╚███╔╝ ██║   ██║                          ║
    ║   ██╔══╝   ██╔██╗ ██║   ██║                          ║
    ║   ███████╗██╔╝ ██╗██║   ██║                          ║
    ║   ╚══════╝╚═╝  ╚═╝╚═╝   ╚═╝                          ║
    ║          ██╗    ██╗ █████╗ ██╗   ██╗███████╗          ║
    ║          ██║    ██║██╔══██╗██║   ██║██╔════╝          ║
    ║          ██║ █╗ ██║███████║██║   ██║█████╗            ║
    ║          ██║███╗██║██╔══██║╚██╗ ██╔╝██╔══╝            ║
    ║          ╚███╔███╔╝██║  ██║ ╚████╔╝ ███████╗          ║
    ║           ╚══╝╚══╝ ╚═╝  ╚═╝  ╚═══╝  ╚══════╝          ║
    ║                                                      ║
    ║   Automated F&O Position Exit System  v{__version__}        ║
    ║   Ride the trade. ExitWave catches the fall.         ║
    ║                                                      ║
    ╚══════════════════════════════════════════════════════╝
    """
    print(banner)


def main():
    """Main entry point for ExitWave."""

    # 1. Build configuration from .env + CLI args
    config = build_config()

    # 2. Set up logging
    logger = setup_logging(config.log_dir, dry_run=config.dry_run)

    _print_banner()

    logger.info(f"{__app_name__} v{__version__} starting...")
    if config.dry_run:
        logger.warning("DRY-RUN MODE — No actual orders will be placed.")

    # 3. Authenticate with Kite
    try:
        kite = authenticate(
            api_key=config.credentials.api_key,
            api_secret=config.credentials.api_secret,
            access_token=config.credentials.access_token,
            force_login=config.force_login,
            redirect_port=config.redirect_port,
            project_root=config.project_root,
            manual_login=config.manual_login,
        )
    except TimeoutError as e:
        logger.error(f"Authentication failed: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Authentication failed: {e}")
        sys.exit(1)

    # 4. Start the position monitor
    monitor = PositionMonitor(kite=kite, config=config)

    # Handle Ctrl+C / termination gracefully
    def signal_handler(sig, frame):
        logger.info("\nShutdown signal received. Stopping monitor...")
        monitor.stop()

    signal.signal(signal.SIGINT, signal_handler)
    if os.name != "nt":  # SIGTERM not reliably available on Windows
        signal.signal(signal.SIGTERM, signal_handler)

    monitor.start()

    logger.info(
        "ExitWave is now monitoring your F&O positions until market close. "
        "Press Ctrl+C to stop."
    )

    # 5. Block main thread until monitor finishes
    try:
        monitor.wait()
    except KeyboardInterrupt:
        logger.info("\nKeyboard interrupt. Stopping monitor...")
        monitor.stop()

    # 6. Final status
    if monitor.has_exited:
        logger.info(
            "ExitWave session ended — exit orders were placed during this session. "
            "See session summary above for details."
        )
    else:
        logger.info("ExitWave session ended — no exit triggered during this session.")
    sys.exit(0)


if __name__ == "__main__":
    main()
