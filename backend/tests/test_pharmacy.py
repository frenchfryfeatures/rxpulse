from decimal import Decimal

from sqlalchemy import func, select

from app.models import Patient, StockBalance, StockLedger
from tests.conftest import BILLING, NURSE, PHARMACIST, RETINA, SURGEON, item_id


async def _sale(c, lines, **extra):
    body = {"channel": "counter_sale", "walk_in_name": "Walk-in", "lines": lines, **extra}
    return await c.post("/pharmacy/orders", json=body)


async def test_otc_walk_in_sale_without_prescription(api, db):
    cmc = await item_id(db, "DRP-CMC-10")
    async with api.as_(PHARMACIST) as c:
        r = await _sale(c, [{"item_id": str(cmc), "qty": 3}])
    assert r.status_code == 201, r.text
    o = r.json()
    assert o["status"] == "allocated" and o["order_no"].startswith("CS-") and o["invoice_no"] is None
    assert o["party_name"] == "Walk-in (walk-in)"
    # 3 × ₹150 MRP incl. 12% GST
    assert Decimal(o["total"]) == Decimal("450.00")
    assert Decimal(o["subtotal"]) == Decimal("401.79") and Decimal(o["gst_amount"]) == Decimal("48.21")


async def test_schedule_h_needs_prescription_and_h1_needs_prescriber(api, db):
    moxi, tram = await item_id(db, "DRP-MOXI-5"), await item_id(db, "CAP-TRAM-50")
    async with api.as_(PHARMACIST) as c:
        r = await _sale(c, [{"item_id": str(moxi), "qty": 1}])
        assert r.status_code == 422 and r.json()["code"] == "PRESCRIPTION_REQUIRED"
        r = await _sale(c, [{"item_id": str(tram), "qty": 1}], prescription_ref="RX-1")
        assert r.status_code == 422 and r.json()["code"] == "PRESCRIBER_REQUIRED"
        r = await _sale(c, [{"item_id": str(tram), "qty": 1}], prescription_ref="RX-1", prescriber_name="Dr. A")
        assert r.status_code == 201


async def test_iol_is_not_dispensed_by_pharmacy(api, db):
    iol = await item_id(db, "IOL-HA-MONO")
    async with api.as_(PHARMACIST) as c:
        r = await _sale(c, [{"item_id": str(iol), "qty": 1}])
    assert r.status_code == 422 and r.json()["code"] == "NOT_DISPENSABLE"


async def test_full_lifecycle_dispatch_invoice_return(api, db):
    moxi, pred = await item_id(db, "DRP-MOXI-5"), await item_id(db, "DRP-PRED-10")
    patient = await db.scalar(select(Patient).where(Patient.mrn == "MRN-100232"))
    async with api.as_(PHARMACIST) as c:
        r = await _sale(c, [{"item_id": str(moxi), "qty": 2}, {"item_id": str(pred), "qty": 1}],
                        patient_id=str(patient.id), walk_in_name=None, prescription_ref="OPD-1",
                        prescriber_name="Dr. Meera Iyer")
        assert r.status_code == 201, r.text
        o = r.json()
        assert o["party_name"] == "Sunita Deshmukh (MRN-100232)"
        assert o["lines"][0]["allocations"][0]["batch_no"] == "MX24B07"  # FEFO, short-dated batch skipped
        pick = (await c.get(f"/pharmacy/orders/{o['id']}/pick-list")).json()
        assert pick["rows"][0]["bin_code"] == "P-A1"

        r = await c.post(f"/pharmacy/orders/{o['id']}/dispatch")
        assert r.status_code == 200 and r.json()["status"] == "dispatched"
        assert r.json()["invoice_no"].startswith("INV-")
        again = await c.post(f"/pharmacy/orders/{o['id']}/dispatch")
        assert again.status_code == 409  # idempotent: can't dispatch twice

        line = o["lines"][0]["id"]
        r = await c.post(f"/pharmacy/orders/{o['id']}/return", json={"lines": [{"line_id": line, "qty": 3}],
                                                                      "reason": "wrong item"})
        assert r.status_code == 422 and r.json()["code"] == "RETURN_EXCEEDS_DISPATCHED"
        r = await c.post(f"/pharmacy/orders/{o['id']}/return", json={"lines": [{"line_id": line, "qty": 1}],
                                                                      "reason": "duplicate purchase"})
        assert r.json()["status"] == "partially_returned" and r.json()["lines"][0]["qty_returned"] == 1
        r = await c.post(f"/pharmacy/orders/{o['id']}/return", json={"lines": [
            {"line_id": line, "qty": 1}, {"line_id": o["lines"][1]["id"], "qty": 1}], "reason": "not needed"})
        assert r.json()["status"] == "returned"
    moves = (await db.execute(select(StockLedger.reason, func.sum(StockLedger.qty_delta))
                              .where(StockLedger.ref_id == o["id"]).group_by(StockLedger.reason))).all()
    assert {m[0].value: m[1] for m in moves} == {"issue": -3, "return_in": 3}


async def test_cancel_releases_reservation(api, db):
    nepa = await item_id(db, "DRP-NEPA-5")

    async def reserved():
        return await db.scalar(select(func.sum(StockBalance.qty_reserved))
                               .where(StockBalance.batch_id.in_(select(StockLedger.batch_id)))
                               .execution_options(populate_existing=True))

    before = await reserved()
    async with api.as_(PHARMACIST) as c:
        o = (await _sale(c, [{"item_id": str(nepa), "qty": 5}], prescription_ref="RX")).json()
        assert await reserved() == before + 5
        r = await c.post(f"/pharmacy/orders/{o['id']}/cancel")
        assert r.json()["status"] == "cancelled"
        assert (await c.post(f"/pharmacy/orders/{o['id']}/dispatch")).status_code == 409
    db.expire_all()
    assert await reserved() == before


async def test_doctor_requisition_flow_and_visibility(api, db):
    bss = await item_id(db, "CON-BSS-500")
    async with api.as_(RETINA) as c:
        # Doctors can't sell at the counter or dispatch
        assert (await _sale(c, [{"item_id": str(bss), "qty": 1}])).status_code == 403
        r = await c.post("/pharmacy/orders", json={"channel": "requisition", "department": "Retina OT",
                                                   "lines": [{"item_id": str(bss), "qty": 4}]})
        assert r.status_code == 201, r.text
        o = r.json()
        assert o["order_no"].startswith("RQ-") and o["requested_by_name"] == "Dr. Meera Iyer"
        assert (await c.post(f"/pharmacy/orders/{o['id']}/dispatch")).status_code == 403
        mine = (await c.get("/pharmacy/orders")).json()
        assert mine["total"] == 1 and mine["items"][0]["id"] == o["id"]
        # Can't raise a requisition in someone else's name
        r = await c.post("/pharmacy/orders", json={"channel": "requisition", "department": "X",
                                                   "requested_by_id": o["created_by_name"] and o["requested_by_id"],
                                                   "lines": [{"item_id": str(bss), "qty": 1}]})
        assert r.status_code == 201  # own id is fine
    async with api.as_(SURGEON) as c:  # another doctor can't see it
        assert (await c.get(f"/pharmacy/orders/{o['id']}")).status_code == 404
    async with api.as_(PHARMACIST) as c:
        r = await c.post(f"/pharmacy/orders/{o['id']}/dispatch")
        assert r.status_code == 200 and r.json()["invoice_no"] is None  # requisitions aren't invoiced


async def test_pharmacist_can_raise_requisition_on_behalf_of_doctor(api, db):
    bss = await item_id(db, "CON-BSS-500")
    async with api.as_(PHARMACIST) as c:
        req = (await c.get("/pharmacy/requesters")).json()
        doc = next(x for x in req if x["display_name"] == "Dr. Rajesh Kulkarni")
        r = await c.post("/pharmacy/orders", json={"channel": "requisition", "department": "OT-2",
                                                   "requested_by_id": doc["id"],
                                                   "lines": [{"item_id": str(bss), "qty": 2}]})
    assert r.status_code == 201 and r.json()["requested_by_name"] == "Dr. Rajesh Kulkarni"
    async with api.as_(NURSE) as c:
        r = await c.post("/pharmacy/orders", json={"channel": "requisition", "department": "OT-2",
                                                   "requested_by_id": doc["id"],
                                                   "lines": [{"item_id": str(bss), "qty": 2}]})
    assert r.status_code == 403


async def test_list_filters_search_and_billing_view(api):
    async with api.as_(BILLING) as c:
        all_ = (await c.get("/pharmacy/orders", params={"page_size": 50})).json()
        sales = (await c.get("/pharmacy/orders", params={"channel": "counter_sale"})).json()
        found = (await c.get("/pharmacy/orders", params={"q": "ramesh"})).json()
        returned = (await c.get("/pharmacy/orders", params={"status": "partially_returned"})).json()
        assert (await c.post("/pharmacy/orders/00000000-0000-0000-0000-000000000000/dispatch")).status_code == 403
    assert all_["total"] == 6 and sales["total"] == 4
    assert found["total"] == 1 and found["items"][0]["patient"]["name"] == "Ramesh Patil"
    assert returned["total"] == 1


async def test_insufficient_stock_reports_every_shortage(api, db):
    rani, sut = await item_id(db, "INJ-RANI-10"), await item_id(db, "CON-SUT-10")
    async with api.as_(PHARMACIST) as c:
        r = await _sale(c, [{"item_id": str(rani), "qty": 50}, {"item_id": str(sut), "qty": 100}],
                        prescription_ref="RX")
    assert r.status_code == 409 and r.json()["code"] == "INSUFFICIENT_STOCK"
    assert {s["item_name"] for s in r.json()["shortages"]} == {
        "Ranibizumab 10mg/ml Injection 0.23ml", "Nylon Suture 10-0"}


async def test_dashboard_is_role_aware(api):
    async with api.as_(PHARMACIST) as c:
        d = (await c.get("/dashboard/summary")).json()
    assert d["orders_awaiting_dispatch"] == 2 and d["counter_sales_today"] is not None
    assert d["expired_on_hand"] == 1
    async with api.as_(RETINA) as c:
        d = (await c.get("/dashboard/summary")).json()
    assert d["stock_value"] is None and d["orders_awaiting_dispatch"] is None
