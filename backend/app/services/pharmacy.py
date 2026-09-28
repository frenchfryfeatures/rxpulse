"""Hospital pharmacy orders.

One pipeline, two channels:
- counter_sale: patients / walk-in buyers at the pharmacy counter (invoiced at dispatch)
- requisition:  doctors, surgeons, OT and wards requesting stock from the pharmacy

create (FEFO reserve) → dispatch (stock issued) → return (partial/full, back into the original batch)
                      ↘ cancel (reservation released)
"""

import uuid
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.errors import AppError, conflict, forbidden, not_found
from app.core.rbac import Principal, ensure
from app.models import (
    DrugSchedule,
    Item,
    ItemType,
    Location,
    OrderChannel,
    OrderStatus,
    Patient,
    PharmacyOrder,
    PharmacyOrderAllocation,
    PharmacyOrderLine,
    StockBalance,
    User,
    UserStatus,
)
from app.models.pharmacy import INVOICE_NO_SEQ, ORDER_NO_SEQ
from app.schemas.pharmacy import (
    AllocationOut,
    OrderCreate,
    OrderLineOut,
    OrderOut,
    PatientOut,
    PickListOut,
    PickListRow,
    ReturnIn,
)
from app.services import audit, stock

CENT = Decimal("0.01")
DISPENSABLE_TYPES = {ItemType.drug, ItemType.consumable}
RX_REQUIRED = {DrugSchedule.H, DrugSchedule.H1, DrugSchedule.X}
PRESCRIBER_REQUIRED = {DrugSchedule.H1, DrugSchedule.X}


async def pharmacy_location(db: AsyncSession) -> Location:
    loc = await db.scalar(select(Location).where(Location.code == get_settings().pharmacy_location_code))
    if loc is None:
        raise AppError(500, "PHARMACY_NOT_CONFIGURED", "The pharmacy location has not been set up")
    return loc


_order_opts = (
    selectinload(PharmacyOrder.lines).selectinload(PharmacyOrderLine.item),
    selectinload(PharmacyOrder.lines).selectinload(PharmacyOrderLine.allocations)
    .selectinload(PharmacyOrderAllocation.batch),
    selectinload(PharmacyOrder.patient),
    selectinload(PharmacyOrder.requested_by),
    selectinload(PharmacyOrder.created_by),
    selectinload(PharmacyOrder.location),
)


async def get_order(db: AsyncSession, order_id: uuid.UUID, *, lock: bool = False) -> PharmacyOrder:
    stmt = select(PharmacyOrder).where(PharmacyOrder.id == order_id).options(*_order_opts)
    if lock:
        stmt = stmt.with_for_update(of=PharmacyOrder)
    o = await db.scalar(stmt)
    if o is None:
        raise not_found("Pharmacy order")
    return o


def can_view_all(p: Principal, location_id: uuid.UUID) -> bool:
    return p.has("pharmacy_order:view", location_id)


def ensure_can_view(p: Principal, o: PharmacyOrder) -> None:
    if can_view_all(p, o.location_id):
        return
    if p.has("requisition:create") and p.user_id in (o.requested_by_id, o.created_by_id):
        return
    raise not_found("Pharmacy order")  # don't reveal existence


def scope_orders(stmt: Select, p: Principal, location: Location) -> Select:
    if can_view_all(p, location.id):
        return stmt.where(PharmacyOrder.location_id == location.id)
    if p.has("requisition:create"):
        return stmt.where(or_(PharmacyOrder.requested_by_id == p.user_id, PharmacyOrder.created_by_id == p.user_id))
    raise forbidden(missing=["pharmacy_order:view"])


def _money(v: Decimal) -> Decimal:
    return v.quantize(CENT, rounding=ROUND_HALF_UP)


def _taxable(gross: Decimal, rate: Decimal) -> Decimal:
    """MRP is GST-inclusive; back out the taxable value."""
    return _money(gross / (Decimal(1) + rate / Decimal(100)))


def _recompute_totals(o: PharmacyOrder) -> None:
    gross = sum((ln.line_total for ln in o.lines), Decimal(0))
    taxable = sum((_taxable(ln.line_total, ln.gst_rate) for ln in o.lines), Decimal(0))
    o.total, o.subtotal, o.gst_amount = _money(gross), _money(taxable), _money(gross - taxable)


async def _next_no(db: AsyncSession, seq, prefix: str) -> str:
    n = await db.scalar(select(seq.next_value()))
    return f"{prefix}-{datetime.now(UTC):%y%m}-{n:05d}"


async def create_order(db: AsyncSession, actor: Principal, data: OrderCreate) -> PharmacyOrder:
    loc = await pharmacy_location(db)
    is_pharmacy_staff = actor.has("pharmacy_order:create", loc.id)
    if data.channel == OrderChannel.counter_sale:
        ensure(actor, "pharmacy_order:create", loc.id)
    elif not (is_pharmacy_staff or actor.has("requisition:create")):
        raise forbidden(missing=["requisition:create"])

    requested_by_id: uuid.UUID | None = None
    if data.channel == OrderChannel.requisition:
        requested_by_id = data.requested_by_id or actor.user_id
        if requested_by_id != actor.user_id:
            if not is_pharmacy_staff:
                raise forbidden("You can only raise requisitions in your own name")
            req_user = await db.get(User, requested_by_id)
            if req_user is None or req_user.status != UserStatus.active:
                raise AppError(422, "VALIDATION_ERROR", "Requesting staff member not found or inactive")

    patient: Patient | None = None
    if data.patient_id:
        patient = await db.get(Patient, data.patient_id)
        if patient is None:
            raise AppError(422, "VALIDATION_ERROR", "Patient not found")

    ids = [ln.item_id for ln in data.lines]
    items = {i.id: i for i in (await db.scalars(select(Item).where(Item.id.in_(ids)))).all()}
    for ln in data.lines:
        item = items.get(ln.item_id)
        if item is None or not item.is_active:
            raise AppError(422, "VALIDATION_ERROR", "One or more items do not exist or are inactive")
        if item.type not in DISPENSABLE_TYPES:
            raise AppError(422, "NOT_DISPENSABLE", f"{item.name} is not dispensed by the pharmacy "
                                                   "(IOLs and equipment go through surgery kits)")

    if data.channel == OrderChannel.counter_sale:
        scheds = {items[ln.item_id].schedule for ln in data.lines}
        if scheds & RX_REQUIRED and not data.prescription_ref:
            names = [items[ln.item_id].name for ln in data.lines if items[ln.item_id].schedule in RX_REQUIRED]
            raise AppError(422, "PRESCRIPTION_REQUIRED",
                           f"A prescription is required for Schedule H/H1/X items: {', '.join(names)}")
        if scheds & PRESCRIBER_REQUIRED and not data.prescriber_name:
            raise AppError(422, "PRESCRIBER_REQUIRED", "Schedule H1/X items require the prescriber's name")

    picks = await stock.reserve_fefo(
        db, [(items[ln.item_id], ln.qty) for ln in data.lines], loc.id, get_settings().min_shelf_life_days
    )

    prefix = "CS" if data.channel == OrderChannel.counter_sale else "RQ"
    o = PharmacyOrder(
        order_no=await _next_no(db, ORDER_NO_SEQ, prefix), channel=data.channel, status=OrderStatus.allocated,
        location_id=loc.id, patient_id=patient.id if patient else None,
        walk_in_name=None if patient else data.walk_in_name, walk_in_phone=None if patient else data.walk_in_phone,
        prescription_ref=data.prescription_ref, prescriber_name=data.prescriber_name,
        requested_by_id=requested_by_id, department=data.department, surgery_ref=data.surgery_ref,
        notes=data.notes, created_by_id=actor.user_id,
    )
    for n, ln in enumerate(data.lines, start=1):
        item = items[ln.item_id]
        line = PharmacyOrderLine(line_no=n, item_id=item.id, qty=ln.qty, unit_price=item.mrp,
                                 gst_rate=item.gst_rate, line_total=_money(item.mrp * ln.qty))
        line.allocations = [PharmacyOrderAllocation(batch_id=p.batch.id, qty=p.qty) for p in picks[item.id]]
        o.lines.append(line)
    _recompute_totals(o)
    db.add(o)
    await db.flush()
    await audit.record(db, actor, "pharmacy_order.create", "pharmacy_order", o.id,
                       after={"order_no": o.order_no, "channel": o.channel.value, "total": str(o.total),
                              "lines": [{"item": str(ln.item_id), "qty": ln.qty} for ln in o.lines]})
    await db.commit()
    return await get_order(db, o.id)


async def dispatch(db: AsyncSession, actor: Principal, order_id: uuid.UUID) -> PharmacyOrder:
    o = await get_order(db, order_id, lock=True)
    ensure(actor, "pharmacy_order:dispatch", o.location_id)
    if o.status != OrderStatus.allocated:
        raise conflict("INVALID_STATUS", f"Only allocated orders can be dispatched (this one is {o.status.value})")
    for line in o.lines:
        for a in line.allocations:
            await stock.issue_reserved(db, a.batch_id, o.location_id, a.qty, actor_id=actor.user_id,
                                       ref_type="pharmacy_order", ref_id=o.id, note=o.order_no)
    o.status = OrderStatus.dispatched
    o.dispatched_at = datetime.now(UTC)
    o.dispatched_by_id = actor.user_id
    if o.channel == OrderChannel.counter_sale:
        o.invoice_no = await _next_no(db, INVOICE_NO_SEQ, "INV")
    await audit.record(db, actor, "pharmacy_order.dispatch", "pharmacy_order", o.id,
                       before={"status": "allocated"}, after={"status": "dispatched", "invoice_no": o.invoice_no})
    await db.commit()
    return await get_order(db, o.id)


async def cancel(db: AsyncSession, actor: Principal, order_id: uuid.UUID) -> PharmacyOrder:
    o = await get_order(db, order_id, lock=True)
    own_requisition = o.channel == OrderChannel.requisition and actor.user_id in (o.requested_by_id, o.created_by_id)
    if not (actor.has("pharmacy_order:create", o.location_id) or own_requisition):
        raise forbidden(missing=["pharmacy_order:create"])
    if o.status != OrderStatus.allocated:
        raise conflict("INVALID_STATUS", "Only orders that have not been dispatched can be cancelled")
    for line in o.lines:
        for a in line.allocations:
            await stock.release(db, a.batch_id, o.location_id, a.qty)
    o.status = OrderStatus.cancelled
    await audit.record(db, actor, "pharmacy_order.cancel", "pharmacy_order", o.id,
                       before={"status": "allocated"}, after={"status": "cancelled"})
    await db.commit()
    return await get_order(db, o.id)


async def return_items(db: AsyncSession, actor: Principal, order_id: uuid.UUID, data: ReturnIn) -> PharmacyOrder:
    o = await get_order(db, order_id, lock=True)
    ensure(actor, "pharmacy_order:return", o.location_id)
    if o.status not in (OrderStatus.dispatched, OrderStatus.partially_returned):
        raise conflict("INVALID_STATUS", "Only dispatched orders can be returned")
    lines = {ln.id: ln for ln in o.lines}
    returned_value = Decimal(0)
    for r in data.lines:
        line = lines.get(r.line_id)
        if line is None:
            raise AppError(422, "VALIDATION_ERROR", "Return line does not belong to this order")
        outstanding = sum(a.qty - a.qty_returned for a in line.allocations)
        if r.qty > outstanding:
            raise AppError(422, "RETURN_EXCEEDS_DISPATCHED",
                           f"{line.item.name}: only {outstanding} unit(s) can still be returned")
        remaining = r.qty
        # Credit back to the latest-expiry batch first (the one least likely to be physically gone).
        for a in sorted(line.allocations, key=lambda a: a.batch.expiry_date, reverse=True):
            take = min(a.qty - a.qty_returned, remaining)
            if take <= 0:
                continue
            a.qty_returned += take
            remaining -= take
            await stock.return_in(db, a.batch_id, o.location_id, take, actor_id=actor.user_id,
                                  ref_type="pharmacy_order", ref_id=o.id, note=f"{o.order_no}: {data.reason}")
            if remaining == 0:
                break
        returned_value += line.unit_price * r.qty
    all_back = all(a.qty_returned == a.qty for ln in o.lines for a in ln.allocations)
    before = o.status.value
    o.status = OrderStatus.returned if all_back else OrderStatus.partially_returned
    await audit.record(db, actor, "pharmacy_order.return", "pharmacy_order", o.id,
                       before={"status": before},
                       after={"status": o.status.value, "reason": data.reason, "refund": str(_money(returned_value)),
                              "lines": [{"line_id": str(r.line_id), "qty": r.qty} for r in data.lines]})
    await db.commit()
    return await get_order(db, o.id)


# ----------------------------------------------------------------------------- output
def party_name(o: PharmacyOrder) -> str:
    if o.channel == OrderChannel.requisition:
        who = o.requested_by.display_name if o.requested_by else "Unknown"
        return f"{who} · {o.department}" if o.department else who
    if o.patient:
        return f"{o.patient.name} ({o.patient.mrn})"
    return f"{o.walk_in_name} (walk-in)"


def order_out(o: PharmacyOrder) -> OrderOut:
    return OrderOut(
        id=o.id, order_no=o.order_no, channel=o.channel, status=o.status, location_id=o.location_id,
        location_name=o.location.name, party_name=party_name(o),
        patient=PatientOut.model_validate(o.patient) if o.patient else None,
        walk_in_name=o.walk_in_name, walk_in_phone=o.walk_in_phone, prescription_ref=o.prescription_ref,
        prescriber_name=o.prescriber_name, requested_by_id=o.requested_by_id,
        requested_by_name=o.requested_by.display_name if o.requested_by else None, department=o.department,
        surgery_ref=o.surgery_ref, notes=o.notes, subtotal=o.subtotal, gst_amount=o.gst_amount, total=o.total,
        invoice_no=o.invoice_no, created_at=o.created_at, created_by_name=o.created_by.display_name,
        dispatched_at=o.dispatched_at,
        lines=[
            OrderLineOut(
                id=ln.id, line_no=ln.line_no, item_id=ln.item_id, item_name=ln.item.name, sku=ln.item.sku,
                schedule=ln.item.schedule.value, qty=ln.qty, unit_price=ln.unit_price, gst_rate=ln.gst_rate,
                line_total=ln.line_total, qty_returned=sum(a.qty_returned for a in ln.allocations),
                allocations=[
                    AllocationOut(batch_id=a.batch_id, batch_no=a.batch.batch_no, expiry_date=a.batch.expiry_date,
                                  qty=a.qty, qty_returned=a.qty_returned)
                    for a in sorted(ln.allocations, key=lambda a: a.batch.expiry_date)
                ],
            )
            for ln in o.lines
        ],
    )


async def pick_list(db: AsyncSession, o: PharmacyOrder) -> PickListOut:
    batch_ids = [a.batch_id for ln in o.lines for a in ln.allocations]
    bins = dict((await db.execute(
        select(StockBalance.batch_id, StockBalance.bin_code)
        .where(StockBalance.batch_id.in_(batch_ids), StockBalance.location_id == o.location_id)
    )).all())
    rows = [
        PickListRow(line_no=ln.line_no, item_name=ln.item.name, sku=ln.item.sku, batch_no=a.batch.batch_no,
                    expiry_date=a.batch.expiry_date, bin_code=bins.get(a.batch_id), qty=a.qty)
        for ln in o.lines for a in sorted(ln.allocations, key=lambda a: a.batch.expiry_date)
    ]
    return PickListOut(order_no=o.order_no, location_name=o.location.name, party_name=party_name(o), rows=rows)


async def count_orders(db: AsyncSession, stmt: Select) -> int:
    return int(await db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
