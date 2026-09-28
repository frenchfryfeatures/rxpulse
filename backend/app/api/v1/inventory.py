import uuid
from datetime import date
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError

from app.api.deps import DB, require
from app.core.config import get_settings
from app.core.errors import conflict, not_found
from app.core.rbac import Principal, ensure
from app.models import Batch, Item, ItemType, Location, StockBalance, StockLedger, User
from app.schemas.common import Page
from app.schemas.inventory import (
    AdjustmentIn,
    BatchRow,
    ExpiryBucket,
    FefoPick,
    FefoPreviewIn,
    FefoPreviewOut,
    ItemCreate,
    ItemOut,
    ItemUpdate,
    LedgerOut,
    ReceiptIn,
    TransferIn,
)
from app.services import audit, stock

router = APIRouter(tags=["inventory"])


def _scoped(stmt, p: Principal, perm: str = "inventory:view"):
    locs = p.locations_for(perm)
    return stmt if locs is None else stmt.where(StockBalance.location_id.in_(locs))


# ----------------------------------------------------------------------------- items
@router.get("/items", response_model=Page[ItemOut])
async def list_items(
    db: DB,
    p: Principal = Depends(require("inventory:view", "pharmacy_order:create", "requisition:create", any_of=True)),
    q: str | None = None,
    type_: ItemType | None = Query(None, alias="type"),
    dispensable: bool = False,
    include_inactive: bool = False,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
) -> Page[ItemOut]:
    stmt = select(Item)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(or_(func.lower(Item.name).like(like), func.lower(Item.sku).like(like),
                              func.lower(Item.generic_name).like(like)))
    if type_:
        stmt = stmt.where(Item.type == type_)
    if dispensable:
        stmt = stmt.where(Item.type.in_([ItemType.drug, ItemType.consumable]))
    if not include_inactive:
        stmt = stmt.where(Item.is_active)
    total = int(await db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    items = (await db.scalars(stmt.order_by(Item.name).offset((page - 1) * page_size).limit(page_size))).all()
    totals = await stock.item_stock_totals(db, [i.id for i in items], p.locations_for("inventory:view")
                                           if p.has("inventory:view") else None)
    out = []
    for i in items:
        oh, av = totals.get(i.id, (0, 0))
        out.append(ItemOut.model_validate(i).model_copy(
            update={"on_hand": oh, "available": av, "below_par": i.par_min > 0 and oh < i.par_min}))
    return Page(items=out, total=total, page=page, page_size=page_size)


@router.post("/items", response_model=ItemOut, status_code=status.HTTP_201_CREATED)
async def create_item(body: ItemCreate, db: DB, p: Principal = Depends(require("item:manage"))) -> ItemOut:
    if await db.scalar(select(Item.id).where(func.lower(Item.sku) == body.sku.lower())):
        raise conflict("SKU_EXISTS", "An item with this SKU already exists")
    item = Item(**body.model_dump())
    db.add(item)
    await db.flush()
    await audit.record(db, p, "item.create", "item", item.id, after=body.model_dump(mode="json"))
    await db.commit()
    return ItemOut.model_validate(item)


@router.patch("/items/{item_id}", response_model=ItemOut)
async def update_item(item_id: uuid.UUID, body: ItemUpdate, db: DB,
                      p: Principal = Depends(require("item:manage"))) -> ItemOut:
    item = await db.get(Item, item_id)
    if item is None:
        raise not_found("Item")
    changes = body.model_dump(exclude_unset=True)
    before = {k: getattr(item, k) for k in changes}
    for k, v in changes.items():
        setattr(item, k, v)
    await audit.record(db, p, "item.update", "item", item.id, before=before, after=changes)
    await db.commit()
    return ItemOut.model_validate(item)


# ----------------------------------------------------------------------------- batches
SortKey = Literal["received_desc", "received_asc", "expiry_asc", "expiry_desc", "name_asc", "qty_desc"]
_SORTS = {
    "received_desc": (Batch.received_at.desc(),), "received_asc": (Batch.received_at.asc(),),
    "expiry_asc": (Batch.expiry_date.asc(),), "expiry_desc": (Batch.expiry_date.desc(),),
    "name_asc": (Item.name.asc(), Batch.expiry_date.asc()), "qty_desc": (StockBalance.qty_on_hand.desc(),),
}


def _batch_row(bal: StockBalance, b: Batch, i: Item, loc: Location) -> BatchRow:
    return BatchRow(
        balance_id=bal.id, batch_id=b.id, item_id=i.id, item_name=i.name, sku=i.sku, item_type=i.type,
        schedule=i.schedule, batch_no=b.batch_no, received_at=b.received_at, expiry_date=b.expiry_date,
        days_to_expiry=(b.expiry_date - date.today()).days, expiry_status=stock.expiry_status(b.expiry_date),
        location_id=loc.id, location_name=loc.name, bin_code=bal.bin_code, qty_on_hand=bal.qty_on_hand,
        qty_reserved=bal.qty_reserved, qty_available=bal.qty_on_hand - bal.qty_reserved,
        unit_cost=b.unit_cost, mrp=b.mrp, valuation=(b.unit_cost * bal.qty_on_hand).quantize(Decimal("0.01")),
    )


@router.get("/batches", response_model=Page[BatchRow])
async def list_batches(
    db: DB,
    p: Principal = Depends(require("inventory:view")),
    q: str | None = None,
    location_id: uuid.UUID | None = None,
    item_id: uuid.UUID | None = None,
    expiry_status: Literal["expired", "critical", "warning", "ok"] | None = None,
    include_empty: bool = False,
    sort: SortKey = "received_desc",
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
) -> Page[BatchRow]:
    stmt = _scoped(stock.batch_rows_query(), p)
    if not include_empty:
        stmt = stmt.where(StockBalance.qty_on_hand > 0)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(or_(func.lower(Item.name).like(like), func.lower(Item.sku).like(like),
                              func.lower(Batch.batch_no).like(like), func.lower(StockBalance.bin_code).like(like)))
    if location_id:
        stmt = stmt.where(StockBalance.location_id == location_id)
    if item_id:
        stmt = stmt.where(Batch.item_id == item_id)
    if (f := stock.expiry_filter(expiry_status)) is not None:
        stmt = stmt.where(f)
    total = int(await db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    rows = (await db.execute(
        stmt.order_by(*_SORTS[sort], StockBalance.id).offset((page - 1) * page_size).limit(page_size)
    )).all()
    return Page(items=[_batch_row(*r) for r in rows], total=total, page=page, page_size=page_size)


@router.get("/batches/{batch_id}/ledger", response_model=list[LedgerOut])
async def batch_ledger(
    batch_id: uuid.UUID, db: DB, p: Principal = Depends(require("inventory:view"))
) -> list[LedgerOut]:
    stmt = _ledger_query().where(StockLedger.batch_id == batch_id)
    locs = p.locations_for("inventory:view")
    if locs is not None:
        stmt = stmt.where(StockLedger.location_id.in_(locs))
    rows = (await db.execute(stmt.order_by(StockLedger.created_at.desc()).limit(200))).all()
    return [_ledger_out(r) for r in rows]


def _ledger_query():
    return (
        select(StockLedger, Batch.batch_no, Item.name, Item.sku, Location.name, User.display_name)
        .join(Batch, Batch.id == StockLedger.batch_id)
        .join(Item, Item.id == Batch.item_id)
        .join(Location, Location.id == StockLedger.location_id)
        .outerjoin(User, User.id == StockLedger.actor_id)
    )


def _ledger_out(row) -> LedgerOut:
    led, batch_no, item_name, sku, loc_name, actor = row
    return LedgerOut.model_validate(led).model_copy(update={
        "batch_no": batch_no, "item_name": item_name, "sku": sku, "location_name": loc_name, "actor_name": actor})


# ----------------------------------------------------------------------------- stock movements
async def _one_row(db: DB, bal: StockBalance) -> BatchRow:
    row = (await db.execute(stock.batch_rows_query().where(StockBalance.id == bal.id))).one()
    return _batch_row(*row)


@router.post("/stock/receipts", response_model=BatchRow, status_code=status.HTTP_201_CREATED)
async def receive(body: ReceiptIn, db: DB, p: Principal = Depends(require("grn:create"))) -> BatchRow:
    ensure(p, "grn:create", body.location_id)
    try:
        bal = await stock.receive(db, **body.model_dump(), actor_id=p.user_id)
    except IntegrityError as e:  # concurrent creation of the same batch/balance
        await db.rollback()
        raise conflict("CONCURRENT_UPDATE", "Another receipt for this batch is in progress, please retry") from e
    await audit.record(db, p, "stock.receive", "batch", bal.batch_id, after=body.model_dump(mode="json"))
    await db.commit()
    return await _one_row(db, bal)


@router.post("/stock/adjustments", response_model=BatchRow)
async def adjust(body: AdjustmentIn, db: DB, p: Principal = Depends(require("inventory:adjust"))) -> BatchRow:
    ensure(p, "inventory:adjust", body.location_id)
    if body.qty_delta < 0 and body.reason in ("damaged", "expired"):
        ensure(p, "inventory:writeoff", body.location_id)
    bal = await stock.adjust(db, **body.model_dump(), actor_id=p.user_id)
    await audit.record(db, p, "stock.adjust", "batch", body.batch_id, after=body.model_dump(mode="json"))
    await db.commit()
    return await _one_row(db, bal)


@router.post("/stock/transfers", response_model=list[BatchRow])
async def transfer(body: TransferIn, db: DB, p: Principal = Depends(require("inventory:transfer"))) -> list[BatchRow]:
    ensure(p, "inventory:transfer", body.from_location_id)
    ensure(p, "inventory:transfer", body.to_location_id)
    src, dst = await stock.transfer(db, **body.model_dump(), actor_id=p.user_id)
    await audit.record(db, p, "stock.transfer", "batch", body.batch_id, after=body.model_dump(mode="json"))
    await db.commit()
    return [await _one_row(db, src), await _one_row(db, dst)]


@router.post("/stock/fefo/preview", response_model=FefoPreviewOut)
async def fefo_preview(
    body: FefoPreviewIn, db: DB, p: Principal = Depends(require("inventory:view"))
) -> FefoPreviewOut:
    ensure(p, "inventory:view", body.location_id)
    cands = await stock.fefo_candidates(db, body.item_id, body.location_id, get_settings().min_shelf_life_days,
                                        lock=False)
    picks, short = stock.plan_fefo(cands, body.qty)
    return FefoPreviewOut(
        item_id=body.item_id, requested=body.qty, allocatable=body.qty - short, shortfall=short,
        picks=[FefoPick(batch_id=pk.batch.id, batch_no=pk.batch.batch_no, expiry_date=pk.batch.expiry_date,
                        qty=pk.qty, bin_code=pk.balance.bin_code) for pk in picks],
    )


@router.get("/stock/expiry-risk", response_model=list[ExpiryBucket])
async def expiry_risk(
    db: DB, p: Principal = Depends(require("inventory:view")), location_id: uuid.UUID | None = None
) -> list[ExpiryBucket]:
    bucket = stock.expiry_bucket_expr().label("bucket")
    stmt = (
        select(bucket, func.count(StockBalance.id), func.sum(StockBalance.qty_on_hand),
               func.sum(StockBalance.qty_on_hand * Batch.unit_cost))
        .select_from(StockBalance).join(Batch, Batch.id == StockBalance.batch_id)
        .where(StockBalance.qty_on_hand > 0).group_by(bucket)
    )
    stmt = _scoped(stmt, p)
    if location_id:
        stmt = stmt.where(StockBalance.location_id == location_id)
    got = {b: (n, u, v) for b, n, u, v in (await db.execute(stmt)).all()}
    order = ["expired", "0-30 days", "31-60 days", "61-90 days", "> 90 days"]
    return [
        ExpiryBucket(bucket=b, batches=int(got.get(b, (0, 0, 0))[0]), units=int(got.get(b, (0, 0, 0))[1] or 0),
                     value=Decimal(got.get(b, (0, 0, 0))[2] or 0).quantize(Decimal("0.01")))
        for b in order
    ]


@router.get("/stock/movements", response_model=Page[LedgerOut])
async def movements(
    db: DB, p: Principal = Depends(require("inventory:view")), location_id: uuid.UUID | None = None,
    reason: str | None = None, page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100),
) -> Page[LedgerOut]:
    stmt = _ledger_query()
    locs = p.locations_for("inventory:view")
    if locs is not None:
        stmt = stmt.where(StockLedger.location_id.in_(locs))
    if location_id:
        stmt = stmt.where(StockLedger.location_id == location_id)
    if reason:
        stmt = stmt.where(StockLedger.reason == reason)
    total = int(await db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    rows = (await db.execute(stmt.order_by(StockLedger.created_at.desc()).offset((page - 1) * page_size)
                             .limit(page_size))).all()
    return Page(items=[_ledger_out(r) for r in rows], total=total, page=page, page_size=page_size)
