import os
import aiosqlite
from pathlib import Path
from typing import Optional

DB_PATH = Path(os.getenv("DB_PATH", str(Path(__file__).parent.parent / "aml_ledger.db")))


async def init_db() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id                     TEXT PRIMARY KEY,
                timestamp              TEXT NOT NULL,
                debtor_name            TEXT,
                debtor_sort_code       TEXT,
                debtor_account         TEXT,
                creditor_name          TEXT,
                creditor_sort_code     TEXT,
                creditor_account       TEXT,
                companies_house_number TEXT,
                amount                 REAL,
                currency               TEXT DEFAULT 'GBP',
                status                 TEXT DEFAULT 'PROCESSING',
                risk_score             TEXT,
                confidence_score       REAL,
                reasoning              TEXT,
                recommended_action     TEXT,
                completed_at           TEXT
            )
        """)
        await db.commit()


async def create_transaction(data: dict) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO transactions (
                id, timestamp, debtor_name, debtor_sort_code, debtor_account,
                creditor_name, creditor_sort_code, creditor_account,
                companies_house_number, amount, currency, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data["id"], data["timestamp"],
                data["debtor_name"], data["debtor_sort_code"], data["debtor_account"],
                data["creditor_name"], data["creditor_sort_code"], data["creditor_account"],
                data.get("companies_house_number"),
                data["amount"], data["currency"], data["status"],
            ),
        )
        await db.commit()


async def update_transaction(tx_id: str, updates: dict) -> None:
    if not updates:
        return
    set_clause = ", ".join(f"{col} = ?" for col in updates)
    values = list(updates.values()) + [tx_id]
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            f"UPDATE transactions SET {set_clause} WHERE id = ?", values
        )
        await db.commit()


async def get_transaction(tx_id: str) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM transactions WHERE id = ?", (tx_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def get_all_transactions() -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM transactions ORDER BY timestamp DESC"
        ) as cursor:
            rows = await cursor.fetchall()
            return {row["id"]: dict(row) for row in rows}
