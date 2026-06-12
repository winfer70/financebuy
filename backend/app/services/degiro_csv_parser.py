"""
degiro_csv_parser.py — DeGiro transaction CSV parser.

Parses exported transaction history from DeGiro broker (Dutch online broker).
DeGiro CSV export columns:
    Date, Time, Product, ISIN, Description, FX, Change, Balance, Order ID

Usage:
    parser = DegiroCSVParser()
    result = parser.parse(csv_bytes)
    for row in result.rows:
        print(row.trade_type, row.product, row.quantity)
"""

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import datetime, date, time as time_type
from decimal import Decimal, InvalidOperation
from typing import List, Optional, Tuple


# ---------------------------------------------------------------------------
# Trade-direction keyword sets (multi-language)
# DeGiro exports in the user's account language. The first word of the
# Description column identifies the action.
# ---------------------------------------------------------------------------

_BUY_WORDS = {
    "buy", "kauf", "achat", "compra", "aankoop", "acquisto", "köp",
    "купить", "買入", "购买",
}

_SELL_WORDS = {
    "sell", "verkauf", "vente", "venta", "verkoop", "vendita", "sälj",
    "продать", "賣出", "卖出",
}

# Canonical column names from DeGiro's CSV header row.
EXPECTED_COLUMNS = [
    "Date", "Time", "Product", "ISIN",
    "Description", "FX", "Change", "Balance", "Order ID",
]


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class DegiroRow:
    """A single parsed and validated trade row from a DeGiro CSV export.

    Attributes:
        trade_date:       Calendar date of the trade (datetime.date).
        trade_time:       Execution time (datetime.time, defaults to midnight).
        product:          Human-readable instrument name, e.g. "Apple Inc".
        isin:             ISIN code, e.g. "US0378331005".
        description:      Raw description string from the CSV.
        trade_type:       "BUY" or "SELL".
        quantity:         Number of units traded (always positive).
        price_per_unit:   Per-unit execution price, parsed from description.
        change_currency:  ISO 4217 currency of the Change column, e.g. "EUR".
        change_amount:    Signed amount; negative for BUY outflow.
        order_id:         DeGiro order ID (may be None for OTC / legacy rows).
        fx_rate:          FX rate column value (may be None if not present).
    """
    trade_date: date
    trade_time: time_type
    product: str
    isin: str
    description: str
    trade_type: str          # "BUY" or "SELL"
    quantity: Decimal
    price_per_unit: Decimal
    change_currency: str
    change_amount: Decimal   # signed — negative for BUY outflow
    order_id: Optional[str]
    fx_rate: Optional[Decimal] = None


@dataclass
class ParseResult:
    """Aggregate result of parsing a DeGiro CSV file.

    Attributes:
        rows:          Successfully parsed trade rows.
        skipped_count: Non-trade rows skipped (dividends, fees, FX, etc.).
        error_count:   Rows (or header) that failed to parse.
        errors:        Human-readable error messages for failed rows.
    """
    rows: List[DegiroRow] = field(default_factory=list)
    skipped_count: int = 0   # non-trade rows (dividends, fees, fx)
    error_count: int = 0
    errors: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

class DegiroCSVParser:
    """Parses DeGiro transaction history CSV exports into structured DegiroRow objects.

    Handles:
    - UTF-8, UTF-8-BOM, Latin-1, and CP1252 encodings.
    - European number formatting (1.234,56) and US formatting (1,234.56).
    - Multi-language description strings for BUY / SELL detection.
    - Graceful skipping of non-trade rows (dividends, fees, FX settlements).
    """

    def parse(self, content: bytes) -> ParseResult:
        """Parse raw CSV bytes and return a ParseResult with trade rows.

        Args:
            content: Raw bytes of the DeGiro CSV export file.

        Returns:
            ParseResult with all successfully parsed DegiroRow objects plus
            counts of skipped and errored rows.
        """
        result = ParseResult()

        text = self._decode(content)
        if text is None:
            result.errors.append(
                "Could not decode file. Ensure it is a UTF-8 or Latin-1 CSV."
            )
            result.error_count += 1
            return result

        reader = csv.DictReader(io.StringIO(text))

        if not reader.fieldnames:
            result.errors.append("CSV file is empty or has no header row.")
            result.error_count += 1
            return result

        # Normalise column names: strip whitespace and UTF-8 BOM character.
        actual_cols = [c.strip().lstrip("\ufeff") for c in reader.fieldnames]
        missing = [c for c in EXPECTED_COLUMNS if c not in actual_cols]
        if missing:
            result.errors.append(
                f"CSV header mismatch. Expected columns: {', '.join(EXPECTED_COLUMNS)}. "
                f"Missing: {', '.join(missing)}."
            )
            result.error_count += 1
            return result

        for row_num, raw_row in enumerate(reader, start=2):
            # Normalise all keys/values: strip whitespace, handle None values.
            row = {
                k.strip().lstrip("\ufeff"): (v.strip() if v else "")
                for k, v in raw_row.items()
            }
            parsed = self._parse_row(row_num, row, result)
            if parsed is not None:
                result.rows.append(parsed)

        return result

    # ------------------------------------------------------------------ #
    # Private helpers                                                       #
    # ------------------------------------------------------------------ #

    def _decode(self, content: bytes) -> Optional[str]:
        """Attempt to decode bytes using common encodings.

        Args:
            content: Raw file bytes.

        Returns:
            Decoded string on success, None if all encodings fail.
        """
        for enc in ("utf-8-sig", "utf-8", "latin-1", "cp1252"):
            try:
                return content.decode(enc)
            except (UnicodeDecodeError, LookupError):
                continue
        return None

    def _parse_row(
        self, row_num: int, row: dict, result: ParseResult
    ) -> Optional[DegiroRow]:
        """Parse a single normalised CSV row dict into a DegiroRow.

        Skips non-trade rows silently (increments skipped_count).
        Records errors for rows that look like trades but fail to parse.

        Args:
            row_num: 1-based line number in the CSV (for error messages).
            row:     Normalised key→value dict for this CSV row.
            result:  Mutable ParseResult — errors and skip count are updated.

        Returns:
            DegiroRow on success, None if the row is skipped or errored.
        """
        description = row.get("Description", "")
        trade_type, quantity, price_per_unit = self._parse_description(description)

        # Not a BUY / SELL row — skip silently (dividend, fee, FX, etc.).
        if trade_type is None:
            result.skipped_count += 1
            return None

        # Parse date — DeGiro uses DD-MM-YYYY, fallback to YYYY-MM-DD.
        raw_date = row.get("Date", "")
        trade_date = None
        for fmt in ("%d-%m-%Y", "%Y-%m-%d"):
            try:
                trade_date = datetime.strptime(raw_date, fmt).date()
                break
            except ValueError:
                continue
        if trade_date is None:
            result.errors.append(
                f"Row {row_num}: Cannot parse date '{raw_date}'"
            )
            result.error_count += 1
            return None

        # Parse time — HH:MM; fall back to midnight on failure.
        try:
            trade_time = datetime.strptime(row.get("Time", ""), "%H:%M").time()
        except ValueError:
            trade_time = datetime.min.time()

        # Parse Change field: "EUR -1500.00" → ("EUR", Decimal("-1500.00"))
        try:
            change_currency, change_amount = self._parse_change_field(
                row.get("Change", "")
            )
        except ValueError as exc:
            result.errors.append(f"Row {row_num}: {exc}")
            result.error_count += 1
            return None

        # Parse optional FX rate.
        fx_rate = None
        fx_str = row.get("FX", "").strip()
        if fx_str:
            try:
                fx_rate = Decimal(fx_str.replace(",", "."))
            except InvalidOperation:
                pass  # Non-critical; leave as None

        isin = row.get("ISIN", "").strip()
        order_id = row.get("Order ID", "").strip() or None
        product = row.get("Product", "").strip()

        # Rows without a product name or ISIN are not actionable trades.
        if not product or not isin:
            result.skipped_count += 1
            return None

        return DegiroRow(
            trade_date=trade_date,
            trade_time=trade_time,
            product=product,
            isin=isin,
            description=description,
            trade_type=trade_type,
            quantity=quantity,
            price_per_unit=price_per_unit,
            change_currency=change_currency,
            change_amount=change_amount,
            order_id=order_id,
            fx_rate=fx_rate,
        )

    def _parse_description(
        self, desc: str
    ) -> Tuple[Optional[str], Optional[Decimal], Optional[Decimal]]:
        """Extract trade_type, quantity, and price-per-unit from a description string.

        DeGiro descriptions follow patterns like:
            "Buy 10 @ 142.30 USD"
            "Kauf 10 Stk. @ 142,30"
            "Sell 5 @ 480.00"

        Non-trade descriptions (dividends, FX, fees) do not start with a
        recognised keyword and return (None, None, None).

        Args:
            desc: Raw Description column value from the CSV row.

        Returns:
            Tuple of (trade_type, quantity, price_per_unit).
            All three are None if the description is not a trade.
        """
        desc_lower = desc.lower().strip()
        words = desc_lower.split()
        if not words:
            return None, None, None

        first_word = words[0]
        trade_type = None
        if any(first_word.startswith(kw) for kw in _BUY_WORDS):
            trade_type = "BUY"
        elif any(first_word.startswith(kw) for kw in _SELL_WORDS):
            trade_type = "SELL"
        else:
            return None, None, None

        # --- quantity: first number after the action word ---
        after_action = desc[len(first_word):].strip()
        qty_search = re.search(r"\b(\d[\d,.]*)\b", after_action)
        quantity = Decimal("1")
        if qty_search:
            try:
                raw_qty = qty_search.group(1).replace(",", ".").replace(" ", "")
                quantity = Decimal(raw_qty)
            except InvalidOperation:
                pass

        # --- price: number immediately following '@' ---
        price = Decimal("0")
        price_search = re.search(r"@\s*([\d,.]+)", desc)
        if price_search:
            try:
                raw_price = price_search.group(1).replace(",", ".")
                price = Decimal(raw_price)
            except InvalidOperation:
                pass

        return trade_type, quantity, price

    def _parse_change_field(self, raw: str) -> Tuple[str, Decimal]:
        """Parse the Change column into a (currency, amount) tuple.

        DeGiro formats Change as "<CURRENCY> <AMOUNT>", e.g.:
            "EUR -1,500.00"   → ("EUR", Decimal("-1500.00"))
            "USD 250.00"      → ("USD", Decimal("250.00"))
            "EUR -1.234,56"   → ("EUR", Decimal("-1234.56"))

        Handles both European comma-decimal and US period-decimal formats.

        Args:
            raw: Raw Change column string.

        Returns:
            Tuple of (ISO-4217 currency code, Decimal amount).

        Raises:
            ValueError: If the field cannot be split or the amount parsed.
        """
        raw = raw.strip()
        if not raw:
            return "EUR", Decimal("0")

        parts = raw.split(None, 1)
        if len(parts) != 2:
            raise ValueError(f"Cannot parse change field: '{raw}'")

        currency = parts[0].upper()
        amount_str = parts[1].strip()

        # Determine decimal separator based on last occurrence of ',' vs '.'.
        if "," in amount_str and "." in amount_str:
            if amount_str.rfind(",") > amount_str.rfind("."):
                # European: 1.234,56 → 1234.56
                amount_str = amount_str.replace(".", "").replace(",", ".")
            else:
                # US: 1,234.56 → 1234.56
                amount_str = amount_str.replace(",", "")
        elif "," in amount_str and "." not in amount_str:
            # Only comma present.
            comma_pos = amount_str.rfind(",")
            digits_after = len(amount_str) - comma_pos - 1
            # Treat as thousands separator if exactly 3 digits follow the comma.
            if digits_after == 3 and amount_str[comma_pos + 1:].isdigit():
                amount_str = amount_str.replace(",", "")
            else:
                amount_str = amount_str.replace(",", ".")

        # Strip any remaining non-numeric characters except '-' and '.'.
        amount_str = re.sub(r"[^\d.\-]", "", amount_str)

        try:
            return currency, Decimal(amount_str)
        except InvalidOperation:
            raise ValueError(
                f"Cannot parse amount '{amount_str}' from Change field '{raw}'"
            )
