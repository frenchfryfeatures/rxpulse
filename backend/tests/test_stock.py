import asyncio
from datetime import date, timedelta

from sqlalchemy import func, select, text

from app.models import StockBalance, StockLedger
from tests.conftest import ADMIN, ANALYST, PHARMACIST, STORE, item_id, location_id


async def test_batches_show_names_valuation_and_server_expiry_status(api):
    async with api.as_(ADMIN) as c:
        rows = (await c.get("/batches", params={"q": "moxifloxacin", "sort": "expiry_asc"})).json()["items"]
    assert [r["batch_no"] for r in rows] == ["MX24A11", "MX24B07", "MX25C02"]
    first = rows[0]
    assert first["item_name"].startswith("Moxifloxacin") and first["sku"] == "DRP-MOXI-5"
    assert first["expiry_status"] == "critical" and first["days_to_expiry"] == 20
    assert rows[1]["expiry_status"] == "ok"
    assert float(first["valuation"]) == round(40 * float(first["unit_cost"]), 2) > 0


async def test_expiry_filters_and_risk_buckets(api):
    async with api.as_(ADMIN) as c:
        expired = (await c.get("/batches", params={"expiry_status": "expired"})).json()["items"]
        risk = {b["bucket"]: b for b in (await c.get("/stock/expiry-risk")).json()}
    assert [r["batch_no"] for r in expired] == ["PA2405"]
    assert risk["expired"]["units"] == 8
    assert risk["0-30 days"]["batches"] >= 3


async def test_fefo_preview_skips_expired_and_short_dated(api, db):
    moxi, pharmacy = await item_id(db, "DRP-MOXI-5"), await location_id(db, "MAIN-PHARMACY")
    async with api.as_(PHARMACIST) as c:
        r = (await c.post("/stock/fefo/preview", json={"item_id": str(moxi), "location_id": str(pharmacy),
                                                       "qty": 10})).json()
    # MX24A11 expires in 20 days (< 30-day minimum shelf life) so FEFO starts with MX24B07
    assert r["picks"][0]["batch_no"].startswith("MX24B07") and r["shortfall"] == 0

    pred = await item_id(db, "DRP-PRED-10")
    async with api.as_(PHARMACIST) as c:
        r = (await c.post("/stock/fefo/preview", json={"item_id": str(pred), "location_id": str(pharmacy),
                                                       "qty": 500})).json()
    # 119 left after the seeded sale; the expired PA2405 batch is skipped
    assert [p["batch_no"] for p in r["picks"]] == ["PA2411"] and r["shortfall"] == 381


async def test_receipt_adjustment_transfer_write_ledger(api, db):
    moxi = await item_id(db, "DRP-MOXI-5")
    store, pharmacy = await location_id(db, "CENTRAL-STORE"), await location_id(db, "MAIN-PHARMACY")
    exp = (date.today() + timedelta(days=700)).isoformat()
    async with api.as_(STORE) as c:
        r = await c.post("/stock/receipts", json={"item_id": str(moxi), "location_id": str(store),
                                                  "batch_no": "MX26NEW", "expiry_date": exp, "qty": 100,
                                                  "unit_cost": "110.00", "bin_code": "C-R9"})
        assert r.status_code == 201, r.text
        batch_id = r.json()["batch_id"]
        r = await c.post("/stock/transfers", json={"batch_id": batch_id, "from_location_id": str(store),
                                                   "to_location_id": str(pharmacy), "qty": 30})
        assert r.status_code == 200, r.text
        assert [x["qty_on_hand"] for x in r.json()] == [70, 30]
        r = await c.post("/stock/adjustments", json={"batch_id": batch_id, "location_id": str(store),
                                                     "qty_delta": -2, "reason": "count_correction",
                                                     "note": "cycle count"})
        assert r.json()["qty_on_hand"] == 68
        r = await c.post("/stock/transfers", json={"batch_id": batch_id, "from_location_id": str(store),
                                                   "to_location_id": str(pharmacy), "qty": 1000})
        assert r.status_code == 409
    total = await db.scalar(select(func.sum(StockLedger.qty_delta)).where(StockLedger.batch_id == batch_id))
    bal = await db.scalar(select(func.sum(StockBalance.qty_on_hand)).where(StockBalance.batch_id == batch_id))
    assert total == bal == 98


async def test_cannot_receive_expired_or_mismatched_batch(api, db):
    moxi, store = await item_id(db, "DRP-MOXI-5"), await location_id(db, "CENTRAL-STORE")
    base = {"item_id": str(moxi), "location_id": str(store), "qty": 1, "unit_cost": "1"}
    async with api.as_(STORE) as c:
        r = await c.post("/stock/receipts", json={**base, "batch_no": "OLD", "expiry_date": "2020-01-01"})
        assert r.status_code == 422
        r = await c.post("/stock/receipts", json={**base, "batch_no": "MX25C02",
                                                  "expiry_date": (date.today() + timedelta(days=5000)).isoformat()})
        assert r.status_code == 422 and r.json()["code"] == "BATCH_EXPIRY_MISMATCH"


async def test_location_scope_enforced_on_writes(api, db):
    # Store keeper is scoped to Central Store + Main Pharmacy; OT Store is off-limits.
    ot = await location_id(db, "OT-STORE")
    bal = await db.scalar(select(StockBalance).where(StockBalance.location_id == ot))
    async with api.as_(STORE) as c:
        r = await c.post("/stock/adjustments", json={"batch_id": str(bal.batch_id), "location_id": str(ot),
                                                     "qty_delta": 1, "reason": "other", "note": "test"})
    assert r.status_code == 403


async def test_writeoff_needs_writeoff_permission(api, db):
    pharmacy = await location_id(db, "MAIN-PHARMACY")
    bal = await db.scalar(select(StockBalance).where(StockBalance.location_id == pharmacy))
    async with api.as_(ANALYST) as c:  # no adjust/writeoff
        r = await c.post("/stock/adjustments", json={"batch_id": str(bal.batch_id), "location_id": str(pharmacy),
                                                     "qty_delta": -1, "reason": "damaged", "note": "broken"})
    assert r.status_code == 403
    async with api.as_(PHARMACIST) as c:
        r = await c.post("/stock/adjustments", json={"batch_id": str(bal.batch_id), "location_id": str(pharmacy),
                                                     "qty_delta": -1, "reason": "damaged", "note": "broken"})
    assert r.status_code == 200


async def test_concurrent_sales_never_oversell(api, db):
    """20 parallel counter sales of 2 units against 30 in-date units: exactly 15 succeed."""
    cmc = await item_id(db, "DRP-CMC-10")  # OTC; 78 units at pharmacy after seed sale → cap it first
    pharmacy = await location_id(db, "MAIN-PHARMACY")
    await db.execute(text("UPDATE stock_balances SET qty_on_hand = 30, qty_reserved = 0 "
                          "WHERE location_id = :l AND batch_id IN (SELECT id FROM batches WHERE item_id = :i)"),
                     {"l": pharmacy, "i": cmc})
    await db.commit()

    async def sell(n):
        async with api.as_(PHARMACIST) as c:
            return await c.post("/pharmacy/orders", json={
                "channel": "counter_sale", "walk_in_name": f"Buyer {n}", "lines": [{"item_id": str(cmc), "qty": 2}]})

    results = await asyncio.gather(*(sell(n) for n in range(20)))
    codes = sorted(r.status_code for r in results)
    assert codes.count(201) == 15 and codes.count(409) == 5, codes
    reserved = await db.scalar(select(func.sum(StockBalance.qty_reserved)).where(StockBalance.location_id == pharmacy)
                               .where(StockBalance.batch_id.in_(select(StockBalance.batch_id))))
    assert reserved >= 30


async def test_movements_are_readable(api):
    async with api.as_(ADMIN) as c:
        page = (await c.get("/stock/movements", params={"reason": "issue"})).json()
    assert page["total"] > 0
    row = page["items"][0]
    assert row["item_name"] and row["batch_no"] and row["location_name"] == "Main Pharmacy"
    assert row["actor_name"] == "Farhan Qureshi" and row["qty_delta"] < 0
