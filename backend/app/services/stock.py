"""Stock ledger, balances and FEFO allocation.

Every change to `stock_balances` happens in the same transaction as a `stock_ledger` insert, with the
balance rows locked (SELECT ... FOR UPDATE), so concurrent dispatches can never oversell a batch.
"""

import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import Select, and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, not_found
from app.models import Batch, Item, LedgerReason, Location, StockBalance, StockLedger

CRITICAL_DAYS = 30
WARNING_DAYS = 90


def expiry_status(expiry: date, today: date | None = None) -> str:
    days = (expiry - (today or date.today())).days
    if days < 0:
        return "expired"
    if days <= CRITICAL_DAYS:
        return "critical"
    if days <= WARNING_DAYS:
        return "warning"
    return "ok"


class InsufficientStock(AppError):
    def __init__(self, shortages: list[dict]):
        names = ", ".join(f"{s['item_name']} (need {s['requested']}, available {s['available']})" for s in shortages)
        super().__init__(409, "INSUFFICIENT_STOCK", f"Not enough in-date stock: {names}", shortages=shortages)


async def _lock_balance(db: AsyncSession, batch_id: uuid.UUID, location_id: uuid.UUID) -> StockBalance | None:
    return await db.scalar(
        select(StockBalance)
        .where(StockBalance.batch_id == batch_id, StockBalance.location_id == location_id)
        .with_for_update()
    )


async def _get_or_create_balance(
    db: AsyncSession, batch_id: uuid.UUID, location_id: uuid.UUID, bin_code: str | None = None
) -> StockBalance:
    bal = await _lock_balance(db, batch_id, location_id)
    if bal is None:
        # ON CONFLICT-free: unique constraint makes a concurrent creator fail and retry at the API level.
        bal = StockBalance(batch_id=batch_id, location_id=location_id, bin_code=bin_code, qty_on_hand=0, qty_reserved=0)
        db.add(bal)
        await db.flush()
    return bal


def _ledger(db: AsyncSession, bal: StockBalance, delta: int, reason: LedgerReason, *, actor_id: uuid.UUID | None,
            note: str | None = None, ref_type: str | None = None, ref_id: object = None) -> None:
    db.add(StockLedger(
        batch_id=bal.batch_id, location_id=bal.location_id, qty_delta=delta, reason=reason, note=note,
        ref_type=ref_type, ref_id=str(ref_id) if ref_id else None, actor_id=actor_id,
    ))


async def receive(
    db: AsyncSession, *, item_id: uuid.UUID, location_id: uuid.UUID, batch_no: str, expiry_date: date,
    qty: int, unit_cost: Decimal, mrp: Decimal | None, mfg_date: date | None = None,
    supplier_name: str | None = None, bin_code: str | None = None, actor_id: uuid.UUID | None,
) -> StockBalance:
    item = await db.get(Item, item_id)
    if item is None:
        raise not_found("Item")
    if await db.get(Location, location_id) is None:
        raise not_found("Location")
    if expiry_date <= date.today():
        raise AppError(422, "VALIDATION_ERROR", "Cannot receive stock that is already expired")
    batch = await db.scalar(select(Batch).where(Batch.item_id == item_id, Batch.batch_no == batch_no))
    if batch is None:
        batch = Batch(item_id=item_id, batch_no=batch_no, expiry_date=expiry_date, mfg_date=mfg_date,
                      mrp=mrp if mrp is not None else item.mrp, unit_cost=unit_cost, supplier_name=supplier_name)
        db.add(batch)
        await db.flush()
    elif batch.expiry_date != expiry_date:
        raise AppError(422, "BATCH_EXPIRY_MISMATCH",
                       f"Batch {batch_no} already exists with expiry {batch.expiry_date.isoformat()}")
    bal = await _get_or_create_balance(db, batch.id, location_id, bin_code)
    bal.qty_on_hand += qty
    if bin_code:
        bal.bin_code = bin_code
    _ledger(db, bal, qty, LedgerReason.receipt, actor_id=actor_id, note=supplier_name, ref_type="receipt")
    await db.flush()
    return bal


async def adjust(db: AsyncSession, *, batch_id: uuid.UUID, location_id: uuid.UUID, qty_delta: int, reason: str,
                 note: str, actor_id: uuid.UUID) -> StockBalance:
    if qty_delta == 0:
        raise AppError(422, "VALIDATION_ERROR", "Adjustment quantity cannot be zero")
    bal = await _lock_balance(db, batch_id, location_id)
    if bal is None:
        raise not_found("Stock for this batch at this location")
    if bal.qty_on_hand + qty_delta < bal.qty_reserved:
        raise AppError(409, "INSUFFICIENT_STOCK",
                       f"Only {bal.qty_on_hand - bal.qty_reserved} unreserved units can be adjusted out")
    bal.qty_on_hand += qty_delta
    is_writeoff = reason in ("damaged", "expired") and qty_delta < 0
    ledger_reason = LedgerReason.writeoff if is_writeoff else LedgerReason.adjustment
    _ledger(db, bal, qty_delta, ledger_reason, actor_id=actor_id, note=f"{reason}: {note}", ref_type="adjustment")
    await db.flush()
    return bal


async def transfer(db: AsyncSession, *, batch_id: uuid.UUID, from_location_id: uuid.UUID, to_location_id: uuid.UUID,
                   qty: int, note: str | None, actor_id: uuid.UUID) -> tuple[StockBalance, StockBalance]:
    if from_location_id == to_location_id:
        raise AppError(422, "VALIDATION_ERROR", "Source and destination must differ")
    # Lock in a stable order to avoid deadlocks between opposite transfers.
    first, second = sorted([from_location_id, to_location_id], key=str)
    await _lock_balance(db, batch_id, first)
    await _lock_balance(db, batch_id, second)
    src = await _lock_balance(db, batch_id, from_location_id)
    if src is None or src.qty_on_hand - src.qty_reserved < qty:
        raise AppError(409, "INSUFFICIENT_STOCK", "Not enough unreserved stock at the source location")
    if await db.get(Location, to_location_id) is None:
        raise not_found("Destination location")
    dst = await _get_or_create_balance(db, batch_id, to_location_id)
    ref = uuid.uuid4()
    src.qty_on_hand -= qty
    dst.qty_on_hand += qty
    _ledger(db, src, -qty, LedgerReason.transfer_out, actor_id=actor_id, note=note, ref_type="transfer", ref_id=ref)
    _ledger(db, dst, qty, LedgerReason.transfer_in, actor_id=actor_id, note=note, ref_type="transfer", ref_id=ref)
    await db.flush()
    return src, dst


@dataclass
class Pick:
    balance: StockBalance
    batch: Batch
    qty: int


async def fefo_candidates(
    db: AsyncSession, item_id: uuid.UUID, location_id: uuid.UUID, min_shelf_life_days: int, *, lock: bool
) -> list[tuple[StockBalance, Batch]]:
    cutoff = date.today() + timedelta(days=min_shelf_life_days)
    stmt = (
        select(StockBalance, Batch)
        .join(Batch, Batch.id == StockBalance.batch_id)
        .where(
            Batch.item_id == item_id,
            StockBalance.location_id == location_id,
            StockBalance.qty_on_hand > StockBalance.qty_reserved,
            Batch.expiry_date > cutoff,
        )
        .order_by(Batch.expiry_date.asc(), Batch.received_at.asc(), Batch.batch_no.asc())
    )
    if lock:
        stmt = stmt.with_for_update(of=StockBalance)
    return list((await db.execute(stmt)).all())


def plan_fefo(candidates: list[tuple[StockBalance, Batch]], qty: int) -> tuple[list[Pick], int]:
    """Greedy earliest-expiry-first plan; returns (picks, shortfall)."""
    picks: list[Pick] = []
    remaining = qty
    for bal, batch in candidates:
        if remaining <= 0:
            break
        take = min(bal.qty_on_hand - bal.qty_reserved, remaining)
        if take > 0:
            picks.append(Pick(bal, batch, take))
            remaining -= take
    return picks, remaining


async def reserve_fefo(
    db: AsyncSession, requests: list[tuple[Item, int]], location_id: uuid.UUID, min_shelf_life_days: int
) -> dict[uuid.UUID, list[Pick]]:
    """Lock + reserve stock for several items atomically. Raises InsufficientStock listing every shortfall."""
    result: dict[uuid.UUID, list[Pick]] = {}
    shortages = []
    # Stable lock order across transactions: by item id.
    for item, qty in sorted(requests, key=lambda r: str(r[0].id)):
        cands = await fefo_candidates(db, item.id, location_id, min_shelf_life_days, lock=True)
        picks, short = plan_fefo(cands, qty)
        if short > 0:
            shortages.append({"item_id": str(item.id), "item_name": item.name, "requested": qty,
                              "available": qty - short})
        result[item.id] = picks
    if shortages:
        raise InsufficientStock(shortages)
    for picks in result.values():
        for p in picks:
            p.balance.qty_reserved += p.qty
    await db.flush()
    return result


async def release(db: AsyncSession, batch_id: uuid.UUID, location_id: uuid.UUID, qty: int) -> None:
    bal = await _lock_balance(db, batch_id, location_id)
    assert bal is not None and bal.qty_reserved >= qty
    bal.qty_reserved -= qty


async def issue_reserved(db: AsyncSession, batch_id: uuid.UUID, location_id: uuid.UUID, qty: int, *,
                         actor_id: uuid.UUID, ref_type: str, ref_id: object, note: str | None = None) -> None:
    bal = await _lock_balance(db, batch_id, location_id)
    assert bal is not None and bal.qty_reserved >= qty and bal.qty_on_hand >= qty
    bal.qty_reserved -= qty
    bal.qty_on_hand -= qty
    _ledger(db, bal, -qty, LedgerReason.issue, actor_id=actor_id, note=note, ref_type=ref_type, ref_id=ref_id)


async def return_in(db: AsyncSession, batch_id: uuid.UUID, location_id: uuid.UUID, qty: int, *,
                    actor_id: uuid.UUID, ref_type: str, ref_id: object, note: str | None = None) -> None:
    bal = await _get_or_create_balance(db, batch_id, location_id)
    bal.qty_on_hand += qty
    _ledger(db, bal, qty, LedgerReason.return_in, actor_id=actor_id, note=note, ref_type=ref_type, ref_id=ref_id)


# ----------------------------------------------------------------------------- queries
def batch_rows_query() -> Select:
    return (
        select(StockBalance, Batch, Item, Location)
        .join(Batch, Batch.id == StockBalance.batch_id)
        .join(Item, Item.id == Batch.item_id)
        .join(Location, Location.id == StockBalance.location_id)
    )


def expiry_filter(status: str | None):
    today = date.today()
    match status:
        case "expired":
            return Batch.expiry_date < today
        case "critical":
            return and_(Batch.expiry_date >= today, Batch.expiry_date <= today + timedelta(days=CRITICAL_DAYS))
        case "warning":
            return and_(Batch.expiry_date > today + timedelta(days=CRITICAL_DAYS),
                        Batch.expiry_date <= today + timedelta(days=WARNING_DAYS))
        case "ok":
            return Batch.expiry_date > today + timedelta(days=WARNING_DAYS)
    return None


def expiry_bucket_expr():
    today = date.today()
    return case(
        (Batch.expiry_date < today, "expired"),
        (Batch.expiry_date <= today + timedelta(days=CRITICAL_DAYS), "0-30 days"),
        (Batch.expiry_date <= today + timedelta(days=60), "31-60 days"),
        (Batch.expiry_date <= today + timedelta(days=WARNING_DAYS), "61-90 days"),
        else_="> 90 days",
    )


async def item_stock_totals(db: AsyncSession, item_ids: list[uuid.UUID],
                            location_ids: set[uuid.UUID] | None) -> dict[uuid.UUID, tuple[int, int]]:
    stmt = (
        select(Batch.item_id, func.coalesce(func.sum(StockBalance.qty_on_hand), 0),
               func.coalesce(func.sum(StockBalance.qty_on_hand - StockBalance.qty_reserved), 0))
        .join(StockBalance, StockBalance.batch_id == Batch.id)
        .where(Batch.item_id.in_(item_ids), Batch.expiry_date >= date.today())
        .group_by(Batch.item_id)
    )
    if location_ids is not None:
        stmt = stmt.where(StockBalance.location_id.in_(location_ids))
    return {iid: (int(oh), int(av)) for iid, oh, av in (await db.execute(stmt)).all()}
