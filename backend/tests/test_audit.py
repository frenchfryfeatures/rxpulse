import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from tests.conftest import ADMIN


async def test_audit_is_append_only_at_db_level(db):
    with pytest.raises(DBAPIError, match="append-only"):
        await db.execute(text("UPDATE audit_log SET action = 'x'"))
    await db.rollback()
    with pytest.raises(DBAPIError, match="append-only"):
        await db.execute(text("DELETE FROM stock_ledger"))
    await db.rollback()


async def test_hash_chain_detects_tampering(api, db):
    async with api.as_(ADMIN) as c:
        assert (await c.get("/audit/verify")).json()["ok"] is True
    # Simulate a DBA bypassing the trigger to rewrite history.
    await db.execute(text("ALTER TABLE audit_log DISABLE TRIGGER audit_log_append_only"))
    await db.execute(text("UPDATE audit_log SET after = '{\"total\": \"1.00\"}' WHERE id = 2"))
    await db.execute(text("ALTER TABLE audit_log ENABLE TRIGGER audit_log_append_only"))
    await db.commit()
    async with api.as_(ADMIN) as c:
        assert (await c.get("/audit/verify")).json() == {"ok": False, "first_bad_id": 2}
