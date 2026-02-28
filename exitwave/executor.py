"""
Order execution engine for ExitWave.

Places exit (square-off) orders for all open F&O positions.
For LONG positions → SELL, for SHORT positions → BUY.
All exit orders are MARKET orders for immediate execution.
"""

import time
from dataclasses import dataclass
from typing import List, Optional

from kiteconnect import KiteConnect

from exitwave.positions import FnOPosition
from exitwave.notifier import get_logger


@dataclass
class ExitOrderResult:
    """Result of a single exit order attempt."""
    tradingsymbol: str
    exchange: str
    transaction_type: str   # BUY or SELL
    quantity: int
    order_id: Optional[str] = None
    success: bool = False
    error: str = ""


def _determine_exit_transaction(position: FnOPosition) -> str:
    """Determine the exit transaction type for a position."""
    if position.quantity > 0:
        return KiteConnect.TRANSACTION_TYPE_SELL
    elif position.quantity < 0:
        return KiteConnect.TRANSACTION_TYPE_BUY
    return ""


def place_exit_order(kite: KiteConnect, position: FnOPosition,
                     dry_run: bool = False) -> ExitOrderResult:
    """
    Place a single exit order for a position.

    Args:
        kite: Authenticated KiteConnect instance.
        position: The F&O position to exit.
        dry_run: If True, simulate without placing.

    Returns:
        ExitOrderResult with order details.
    """
    log = get_logger()
    transaction_type = _determine_exit_transaction(position)
    quantity = abs(position.quantity)

    if not transaction_type:
        return ExitOrderResult(
            tradingsymbol=position.tradingsymbol,
            exchange=position.exchange,
            transaction_type="NONE",
            quantity=0,
            success=False,
            error="Position has zero quantity, nothing to exit.",
        )

    result = ExitOrderResult(
        tradingsymbol=position.tradingsymbol,
        exchange=position.exchange,
        transaction_type=transaction_type,
        quantity=quantity,
    )

    action_str = f"{transaction_type} {quantity} {position.tradingsymbol} @ MARKET"

    if dry_run:
        log.info(f"[DRY-RUN] EXIT ORDER: {action_str}")
        result.success = True
        result.order_id = "DRY_RUN"
        return result

    # Place the actual market order
    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            order_id = kite.place_order(
                variety=KiteConnect.VARIETY_REGULAR,
                exchange=position.exchange,
                tradingsymbol=position.tradingsymbol,
                transaction_type=transaction_type,
                quantity=quantity,
                product=position.product,
                order_type=KiteConnect.ORDER_TYPE_MARKET,
                validity=KiteConnect.VALIDITY_DAY,
                tag="ExitWave",
            )
            result.order_id = order_id
            result.success = True
            log.info(f"EXIT ORDER: {action_str} -> Order ID: {order_id}")
            return result

        except Exception as e:
            error_msg = str(e)
            log.warning(
                f"Exit order attempt {attempt}/{max_retries} failed for "
                f"{position.tradingsymbol}: {error_msg}"
            )
            result.error = error_msg
            if attempt < max_retries:
                time.sleep(1)  # Brief pause before retry

    log.error(f"FAILED to exit {position.tradingsymbol} after {max_retries} attempts: {result.error}")
    return result


def exit_all_positions(kite: KiteConnect, positions: List[FnOPosition],
                       dry_run: bool = False) -> List[ExitOrderResult]:
    """
    Exit all given F&O positions.

    Args:
        kite: Authenticated KiteConnect instance.
        positions: List of open F&O positions to exit.
        dry_run: If True, simulate without placing orders.

    Returns:
        List of ExitOrderResult for each position.
    """
    log = get_logger()

    if not positions:
        log.info("No positions to exit.")
        return []

    mode = "[DRY-RUN] " if dry_run else ""
    log.critical(
        f"{mode}THRESHOLD BREACHED! Exiting {len(positions)} open F&O position(s)..."
    )

    results = []
    for pos in positions:
        result = place_exit_order(kite, pos, dry_run=dry_run)
        results.append(result)

    # Summary
    successful = sum(1 for r in results if r.success)
    failed = sum(1 for r in results if not r.success)

    if failed == 0:
        log.info(f"{mode}All {successful} exit order(s) placed successfully.")
    else:
        log.error(
            f"{mode}Exit orders: {successful} succeeded, {failed} FAILED. "
            f"Check logs for details."
        )
        for r in results:
            if not r.success:
                log.error(f"  FAILED: {r.transaction_type} {r.quantity} {r.tradingsymbol} — {r.error}")

    return results


def verify_exit_orders(kite: KiteConnect, results: List[ExitOrderResult],
                       dry_run: bool = False) -> bool:
    """
    Verify that all exit orders were executed.

    Args:
        kite: Authenticated KiteConnect instance.
        results: List of ExitOrderResult from exit_all_positions.
        dry_run: If True, skip verification.

    Returns:
        True if all orders completed, False otherwise.
    """
    log = get_logger()

    if dry_run:
        log.info("[DRY-RUN] Skipping order verification.")
        return True

    successful_results = [r for r in results if r.success and r.order_id]
    if not successful_results:
        return False

    log.info("Verifying exit order statuses...")
    time.sleep(2)  # Brief wait for orders to process

    all_completed = True
    for result in successful_results:
        try:
            order_history = kite.order_history(result.order_id)
            if order_history:
                latest = order_history[-1]
                status = latest.get("status", "UNKNOWN")
                if status == "COMPLETE":
                    log.info(
                        f"  CONFIRMED: {result.tradingsymbol} — "
                        f"Order {result.order_id} COMPLETE"
                    )
                elif status == "REJECTED":
                    log.error(
                        f"  REJECTED: {result.tradingsymbol} — "
                        f"Order {result.order_id}: {latest.get('status_message', '')}"
                    )
                    all_completed = False
                else:
                    log.warning(
                        f"  PENDING: {result.tradingsymbol} — "
                        f"Order {result.order_id} status: {status}"
                    )
                    all_completed = False
        except Exception as e:
            log.error(f"  Error checking order {result.order_id}: {e}")
            all_completed = False

    return all_completed
