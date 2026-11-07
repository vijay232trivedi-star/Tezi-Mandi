"""Local, persistent storage for independent BUY and SELL journal entries."""

import datetime as dt
import os
import sqlite3
from contextlib import contextmanager
from decimal import Decimal, InvalidOperation
from pathlib import Path
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
TRADE_COLUMNS = ["id", "trade_date", "trade_time", "side", "symbol", "quantity", "price", "notes"]


def market_now() -> dt.datetime:
    return dt.datetime.now(IST)


class JournalStore:
    def __init__(self, path=None):
        self.path = Path(path or os.environ.get("TRADING_JOURNAL_DB") or
                         Path(__file__).parent / "data" / "trading_journal.sqlite3")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as connection:
            connection.execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trade_date TEXT NOT NULL,
                    trade_time TEXT NOT NULL,
                    side TEXT NOT NULL CHECK (side IN ('BUY', 'SELL')),
                    symbol TEXT NOT NULL CHECK (length(trim(symbol)) > 0),
                    quantity INTEGER CHECK (quantity > 0),
                    price_paise INTEGER CHECK (price_paise > 0),
                    notes TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                )
            """)
            connection.execute("CREATE INDEX IF NOT EXISTS trades_date ON trades(trade_date)")

    @contextmanager
    def _connection(self):
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    @staticmethod
    def _values(*, trade_date, trade_time, side, symbol, quantity=None, price=None, notes=""):
        symbol = " ".join(symbol.strip().upper().split())
        if not symbol:
            raise ValueError("Enter a stock name or symbol.")
        if side not in ("BUY", "SELL"):
            raise ValueError("Trade side must be BUY or SELL.")
        if not isinstance(trade_date, dt.date) or isinstance(trade_date, dt.datetime):
            raise ValueError("Choose a valid trade date.")
        if trade_date > market_now().date():
            raise ValueError("Trade date cannot be in the future.")
        if not isinstance(trade_time, dt.time):
            raise ValueError("Choose a valid trade time.")
        if quantity is not None and (isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 1):
            raise ValueError("Quantity must be a positive whole number.")
        price_paise = None
        if price is not None:
            try:
                value = Decimal(str(price))
                if not value.is_finite() or value <= 0:
                    raise ValueError("Price must be greater than zero.")
                price_paise = int(value.quantize(Decimal("0.01")) * 100)
                if price_paise < 1:
                    raise ValueError("Price must be at least ₹0.01.")
                if price_paise > 9223372036854775807:
                    raise ValueError("Price is too large.")
            except (InvalidOperation, OverflowError) as error:
                raise ValueError("Enter a valid price.") from error
        if quantity is not None and quantity > 9223372036854775807:
            raise ValueError("Quantity is too large.")
        return (trade_date.isoformat(), trade_time.strftime("%H:%M:%S"), side,
                symbol, quantity, price_paise, notes.strip())

    def add_trade(self, **trade) -> int:
        values = self._values(**trade)
        with self._connection() as connection:
            cursor = connection.execute("""
                INSERT INTO trades
                    (trade_date, trade_time, side, symbol, quantity, price_paise, notes, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (*values, market_now().isoformat()))
            return cursor.lastrowid

    def update_trade(self, trade_id: int, **trade):
        values = self._values(**trade)
        with self._connection() as connection:
            cursor = connection.execute("""
                UPDATE trades SET trade_date = ?, trade_time = ?, side = ?, symbol = ?,
                    quantity = ?, price_paise = ?, notes = ? WHERE id = ?
            """, (*values, trade_id))
            if cursor.rowcount != 1:
                raise ValueError("This trade no longer exists. Refresh the journal.")

    def delete_trade(self, trade_id: int):
        with self._connection() as connection:
            cursor = connection.execute("DELETE FROM trades WHERE id = ?", (trade_id,))
            if cursor.rowcount != 1:
                raise ValueError("This trade no longer exists. Refresh the journal.")

    def list_trades(self, start: dt.date = None, end: dt.date = None) -> list[dict]:
        conditions, parameters = [], []
        if start is not None:
            conditions.append("trade_date >= ?")
            parameters.append(start.isoformat())
        if end is not None:
            conditions.append("trade_date <= ?")
            parameters.append(end.isoformat())
        where = " WHERE " + " AND ".join(conditions) if conditions else ""
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT id, trade_date, trade_time, side, symbol, quantity, "
                "price_paise, notes FROM trades" + where +
                " ORDER BY trade_date DESC, trade_time DESC, id DESC", parameters
            ).fetchall()
        trades = []
        for row in rows:
            trade = dict(row)
            paise = trade.pop("price_paise")
            trade["price"] = paise / 100 if paise is not None else None
            trades.append(trade)
        return trades
