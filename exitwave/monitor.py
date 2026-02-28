"""
Position monitoring engine for ExitWave.

Runs as a background thread that:
  - Polls kite.positions() at a configurable interval
  - Filters for F&O positions on specified exchanges
  - Computes aggregate unrealized P&L
  - Triggers exit when max loss threshold is breached
  - Stops at market close time (default 15:30 IST)
"""

import threading
import time
from datetime import datetime, timedelta
from typing import List, Optional

import pytz

from kiteconnect import KiteConnect

from exitwave.config import ExitWaveConfig
from exitwave.executor import exit_all_positions, verify_exit_orders
from exitwave.notifier import get_logger
from exitwave.positions import (
    get_open_fno_positions,
    calculate_total_pnl,
    format_positions_summary,
    FnOPosition,
)

IST = pytz.timezone("Asia/Kolkata")


class PositionMonitor:
    """
    Background position monitor that polls F&O positions and
    triggers automatic exit when the loss threshold is breached.
    """

    def __init__(self, kite: KiteConnect, config: ExitWaveConfig):
        self.kite = kite
        self.config = config
        self.log = get_logger()

        # Parse market close time
        close_parts = config.market_close.split(":")
        self._close_hour = int(close_parts[0])
        self._close_minute = int(close_parts[1])

        # State
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._exit_count = 0           # Number of exit events triggered
        self._all_exit_results = []    # All exit order results across events
        self._exited_symbols: set = set()  # Symbols already exited (avoid re-exit)
        self._last_exit_time: Optional[datetime] = None
        self._exit_cooldown = 30       # Seconds to wait after exit before checking again

        # Stats
        self._poll_count = 0
        self._last_pnl: Optional[float] = None
        self._peak_loss: float = 0.0  # Track worst P&L seen

    @property
    def is_running(self) -> bool:
        """Check if the monitor thread is alive."""
        return self._thread is not None and self._thread.is_alive()

    @property
    def has_exited(self) -> bool:
        """Check if any exit orders have been placed during this session."""
        return self._exit_count > 0

    def start(self):
        """Start the position monitoring background thread."""
        if self.is_running:
            self.log.warning("Monitor is already running.")
            return

        self._stop_event.clear()
        self._exit_count = 0
        self._all_exit_results = []
        self._exited_symbols = set()
        self._last_exit_time = None
        self._poll_count = 0
        self._peak_loss = 0.0

        self._thread = threading.Thread(
            target=self._monitor_loop,
            name="ExitWave-Monitor",
            daemon=True,
        )
        self._thread.start()
        self.log.info("Position monitor started.")

    def stop(self):
        """Signal the monitor to stop."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=30)
            self.log.info("Position monitor stopped.")

    def wait(self):
        """Block until the monitor thread finishes."""
        if self._thread is not None:
            self._thread.join()

    def _is_market_open(self) -> bool:
        """Check if current IST time is before market close."""
        now = datetime.now(IST)
        close_time = now.replace(
            hour=self._close_hour,
            minute=self._close_minute,
            second=0,
            microsecond=0,
        )
        return now < close_time

    def _monitor_loop(self):
        """Main monitoring loop — runs in background thread."""
        log = self.log
        config = self.config

        log.info("=" * 60)
        log.info(f"  ExitWave Monitor Active")
        log.info(f"  Max Loss Threshold : Rs.{config.max_loss:,.2f}")
        log.info(f"  Poll Interval      : {config.poll_interval}s")
        log.info(f"  Market Close       : {config.market_close} IST")
        log.info(f"  Exchanges          : {', '.join(config.exchanges)}")
        log.info(f"  Dry Run            : {config.dry_run}")
        log.info("=" * 60)

        while not self._stop_event.is_set():
            # Check market hours
            if not self._is_market_open():
                log.info(
                    f"Market close time ({config.market_close} IST) reached. "
                    f"Stopping monitor."
                )
                break

            # If in exit cooldown, skip polling
            if self._last_exit_time is not None:
                elapsed = (datetime.now(IST) - self._last_exit_time).total_seconds()
                if elapsed < self._exit_cooldown:
                    remaining = int(self._exit_cooldown - elapsed)
                    if remaining % 10 == 0 and remaining > 0:
                        log.info(f"Post-exit cooldown: resuming monitoring in {remaining}s...")
                    self._stop_event.wait(timeout=1)
                    continue

            # Poll positions
            try:
                self._poll_positions()
            except Exception as e:
                log.error(f"Error during position poll: {e}")
                self._handle_poll_error(e)

            # Wait for next poll
            self._stop_event.wait(timeout=config.poll_interval)

        log.info("Monitor loop ended.")
        self._print_session_summary()

    def _poll_positions(self):
        """Single poll cycle: fetch positions, check P&L, maybe exit."""
        log = self.log
        config = self.config
        self._poll_count += 1

        # Fetch open F&O positions
        positions = get_open_fno_positions(self.kite, config.exchanges)

        if not positions:
            if self._poll_count % 6 == 1:  # Log every ~60s if no positions
                log.info("No open F&O positions found. Continuing to monitor...")
            return

        # Calculate total P&L
        total_pnl = calculate_total_pnl(positions)
        self._last_pnl = total_pnl

        # Track peak loss
        if total_pnl < self._peak_loss:
            self._peak_loss = total_pnl

        # Log current state
        now_str = datetime.now(IST).strftime("%H:%M:%S")
        position_count = len(positions)
        pnl_str = f"Rs.{total_pnl:+,.2f}"
        threshold_str = f"Rs.{-config.max_loss:,.2f}"

        # Determine log level based on proximity to threshold
        loss_ratio = abs(total_pnl) / config.max_loss if total_pnl < 0 else 0

        if loss_ratio >= 1.0:
            # THRESHOLD BREACHED — EXIT
            log.critical(
                f"THRESHOLD BREACHED! P&L: {pnl_str} | "
                f"Threshold: {threshold_str} | "
                f"Positions: {position_count}"
            )
            self._trigger_exit(positions, total_pnl)
            return
        elif loss_ratio >= 0.8:
            log.warning(
                f"[{now_str}] P&L: {pnl_str} | "
                f"Threshold: {threshold_str} ({loss_ratio:.0%}) | "
                f"Positions: {position_count} | APPROACHING THRESHOLD"
            )
        elif loss_ratio >= 0.5:
            log.warning(
                f"[{now_str}] P&L: {pnl_str} | "
                f"Threshold: {threshold_str} ({loss_ratio:.0%}) | "
                f"Positions: {position_count}"
            )
        else:
            log.info(
                f"[{now_str}] P&L: {pnl_str} | "
                f"Threshold: {threshold_str} | "
                f"Positions: {position_count}"
            )

        # Every 30 polls (~5 min at 10s interval), log detailed positions
        if self._poll_count % 30 == 0:
            summary = format_positions_summary(positions, total_pnl)
            log.info(f"\n{summary}")

    def _trigger_exit(self, positions: List[FnOPosition], total_pnl: float):
        """Execute the exit of all open F&O positions, then continue monitoring."""
        log = self.log
        self._exit_count += 1

        log.critical(
            f"Initiating emergency exit #{self._exit_count} for {len(positions)} position(s). "
            f"Total P&L: Rs.{total_pnl:+,.2f}"
        )

        # Log each position being exited
        for pos in positions:
            log.info(f"  Exiting: {pos}")

        # Place exit orders
        results = exit_all_positions(
            self.kite, positions, dry_run=self.config.dry_run
        )
        self._all_exit_results.extend(results)

        # Track exited symbols so we don't re-exit them immediately
        for pos in positions:
            self._exited_symbols.add(pos.tradingsymbol)

        # Verify orders
        if not self.config.dry_run:
            verify_exit_orders(self.kite, results, dry_run=self.config.dry_run)

        # Start cooldown — continue monitoring after a pause
        self._last_exit_time = datetime.now(IST)
        log.info(
            f"Exit #{self._exit_count} complete. Resuming monitoring in "
            f"{self._exit_cooldown}s (watching for new positions until market close)..."
        )

    def _handle_poll_error(self, error: Exception):
        """Handle errors during position polling with retry logic."""
        log = self.log
        error_name = type(error).__name__

        # Check for authentication errors
        if "Token" in error_name or "token" in str(error).lower():
            log.error(
                "Authentication error — access token may have expired. "
                "Please restart ExitWave with --login flag."
            )
            self._stop_event.set()
            return

        # For network errors, wait a bit longer before next poll
        log.warning(f"Will retry in {self.config.poll_interval * 2}s...")
        self._stop_event.wait(timeout=self.config.poll_interval)

    def _print_session_summary(self):
        """Print a summary of the monitoring session."""
        log = self.log
        log.info("")
        log.info("=" * 60)
        log.info("  ExitWave Session Summary")
        log.info("=" * 60)
        log.info(f"  Total polls         : {self._poll_count}")
        log.info(f"  Last P&L            : Rs.{self._last_pnl:+,.2f}" if self._last_pnl is not None else "  Last P&L            : N/A")
        log.info(f"  Peak loss           : Rs.{self._peak_loss:+,.2f}")
        log.info(f"  Threshold           : Rs.{-self.config.max_loss:,.2f}")
        log.info(f"  Exit events         : {self._exit_count}")

        if self._all_exit_results:
            successful = sum(1 for r in self._all_exit_results if r.success)
            failed = sum(1 for r in self._all_exit_results if not r.success)
            log.info(f"  Total exit orders   : {successful} succeeded, {failed} failed")

        log.info("=" * 60)
