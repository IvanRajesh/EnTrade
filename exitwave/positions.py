"""
Position data parsing and P&L calculation for ExitWave.

Responsible for:
  - Fetching positions from Kite
  - Filtering F&O positions by exchange
  - Computing aggregate unrealized P&L
  - Determining which positions need exit orders
"""

from dataclasses import dataclass
from typing import List, Dict, Any

from kiteconnect import KiteConnect

from exitwave.notifier import get_logger


@dataclass
class FnOPosition:
    """Parsed representation of a single F&O position."""
    tradingsymbol: str
    exchange: str
    instrument_token: int
    product: str          # NRML or MIS
    quantity: int         # +ve = long, -ve = short
    average_price: float
    last_price: float
    pnl: float            # Unrealized P&L from Kite
    m2m: float            # Mark-to-market P&L
    buy_quantity: int
    sell_quantity: int
    buy_price: float
    sell_price: float

    @property
    def is_open(self) -> bool:
        """Position is open if net quantity is non-zero."""
        return self.quantity != 0

    @property
    def side(self) -> str:
        """Returns 'LONG' if positive qty, 'SHORT' if negative."""
        if self.quantity > 0:
            return "LONG"
        elif self.quantity < 0:
            return "SHORT"
        return "FLAT"

    def __str__(self) -> str:
        side = self.side
        qty = abs(self.quantity)
        return (
            f"{self.tradingsymbol} | {side} {qty} | "
            f"Avg: {self.average_price:.2f} | LTP: {self.last_price:.2f} | "
            f"P&L: {self.pnl:+.2f}"
        )


def fetch_positions(kite: KiteConnect) -> Dict[str, Any]:
    """
    Fetch all positions from Kite.

    Returns:
        Raw positions dict with 'net' and 'day' keys.
    """
    return kite.positions()


def parse_fno_positions(raw_positions: Dict[str, Any],
                        exchanges: List[str]) -> List[FnOPosition]:
    """
    Parse raw Kite positions and filter for F&O positions on given exchanges.

    Args:
        raw_positions: Raw dict from kite.positions().
        exchanges: List of exchanges to include (e.g., ["NFO", "BFO"]).

    Returns:
        List of FnOPosition objects for matching open positions.
    """
    positions = []

    for pos in raw_positions.get("net", []):
        if pos.get("exchange", "") not in exchanges:
            continue

        fno_pos = FnOPosition(
            tradingsymbol=pos.get("tradingsymbol", ""),
            exchange=pos.get("exchange", ""),
            instrument_token=pos.get("instrument_token", 0),
            product=pos.get("product", ""),
            quantity=pos.get("quantity", 0),
            average_price=pos.get("average_price", 0.0),
            last_price=pos.get("last_price", 0.0),
            pnl=pos.get("pnl", 0.0),
            m2m=pos.get("m2m", 0.0),
            buy_quantity=pos.get("buy_quantity", 0),
            sell_quantity=pos.get("sell_quantity", 0),
            buy_price=pos.get("buy_price", 0.0),
            sell_price=pos.get("sell_price", 0.0),
        )
        positions.append(fno_pos)

    return positions


def get_open_fno_positions(kite: KiteConnect,
                           exchanges: List[str]) -> List[FnOPosition]:
    """
    Fetch and return only open F&O positions (non-zero quantity).

    Args:
        kite: Authenticated KiteConnect instance.
        exchanges: Exchanges to filter (e.g., ["NFO", "BFO"]).

    Returns:
        List of open FnOPosition objects.
    """
    raw = fetch_positions(kite)
    all_fno = parse_fno_positions(raw, exchanges)
    return [p for p in all_fno if p.is_open]


def calculate_total_pnl(positions: List[FnOPosition]) -> float:
    """
    Calculate the aggregate unrealized P&L across all positions.

    Args:
        positions: List of FnOPosition objects.

    Returns:
        Total P&L in ₹ (negative means loss).
    """
    return sum(p.pnl for p in positions)


def format_positions_summary(positions: List[FnOPosition], total_pnl: float) -> str:
    """
    Create a human-readable summary of current positions.

    Args:
        positions: List of open F&O positions.
        total_pnl: Aggregate P&L.

    Returns:
        Formatted multi-line string.
    """
    if not positions:
        return "No open F&O positions."

    lines = [f"Open F&O Positions ({len(positions)}):"]
    lines.append("-" * 80)
    for pos in positions:
        lines.append(f"  {pos}")
    lines.append("-" * 80)
    lines.append(f"  Total P&L: {total_pnl:+,.2f}")
    return "\n".join(lines)
