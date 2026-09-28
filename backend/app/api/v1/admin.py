import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select

from app.api.deps import DB, CurrentPrincipal, require
from app.core.rbac import Principal
from app.models import AuditLog, Batch, Item, OrderChannel, OrderStatus, PharmacyOrder, StockBalance
from app.schemas.common import ORM, Page
from app.services import audit, pharmacy, stock

router = APIRouter(tags=["admin"])


class AuditOut(ORM):
    id: int
    ts: datetime
    actor_id: uuid.UUID | None
    actor_email: str | None
    actor_type: str
    action: str
    entity_type: str
    entity_id: str | None
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    ip: str | None


@router.get("/audit", response_model=Page[AuditOut])
async def list_audit(
    db: DB, p: Principal = Depends(require("audit:view")),
    action: str | None = None, entity_type: str | None = None, entity_id: str | None = None,
    actor: str | None = None, page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100),
) -> Page[AuditOut]:
    stmt = select(AuditLog)
    if action:
        stmt = stmt.where(AuditLog.action.like(f"{action}%"))
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    if entity_id:
        stmt = stmt.where(AuditLog.entity_id == entity_id)
    if actor:
        stmt = stmt.where(func.lower(AuditLog.actor_email).like(f"%{actor.lower()}%"))
    total = int(await db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    rows = (await db.scalars(stmt.order_by(AuditLog.id.desc()).offset((page - 1) * page_size).limit(page_size))).all()
    return Page(items=[AuditOut.model_validate(r) for r in rows], total=total, page=page, page_size=page_size)


class AuditVerifyOut(BaseModel):
    ok: bool
    first_bad_id: int | None


@router.get("/audit/verify", response_model=AuditVerifyOut)
async def verify_audit(db: DB, p: Principal = Depends(require("audit:view"))) -> AuditVerifyOut:
    ok, bad = await audit.verify_chain(db)
    return AuditVerifyOut(ok=ok, first_bad_id=bad)


class DashboardOut(BaseModel):
    stock_value: Decimal | None
    active_batches: int | None
    expiring_30: int | None
    expired_on_hand: int | None
    below_par_items: int | None
    orders_awaiting_dispatch: int | None
    counter_sales_today: Decimal | None
    requisitions_today: int | None


@router.get("/dashboard/summary", response_model=DashboardOut)
async def dashboard(p: CurrentPrincipal, db: DB) -> DashboardOut:
    """Role-aware KPIs: tiles the caller can't see are returned as null."""
    out = DashboardOut(stock_value=None, active_batches=None, expiring_30=None, expired_on_hand=None,
                       below_par_items=None, orders_awaiting_dispatch=None, counter_sales_today=None,
                       requisitions_today=None)
    today = date.today()
    if p.has("inventory:view"):
        base = select(StockBalance).join(Batch, Batch.id == StockBalance.batch_id).where(StockBalance.qty_on_hand > 0)
        locs = p.locations_for("inventory:view")
        if locs is not None:
            base = base.where(StockBalance.location_id.in_(locs))
        sub = base.subquery()
        out.active_batches = int(await db.scalar(
            select(func.count()).select_from(base.where(Batch.expiry_date >= today).subquery())) or 0)
        out.stock_value = Decimal(await db.scalar(
            select(func.coalesce(func.sum(sub.c.qty_on_hand * Batch.unit_cost), 0))
            .select_from(sub).join(Batch, Batch.id == sub.c.batch_id).where(Batch.expiry_date >= today)
        ) or 0).quantize(Decimal("0.01"))
        out.expiring_30 = int(await db.scalar(select(func.count()).select_from(
            base.where(stock.expiry_filter("critical")).subquery())) or 0)
        out.expired_on_hand = int(await db.scalar(select(func.count()).select_from(
            base.where(stock.expiry_filter("expired")).subquery())) or 0)
        on_hand = (
            select(Batch.item_id, func.sum(StockBalance.qty_on_hand).label("oh"))
            .join(StockBalance, StockBalance.batch_id == Batch.id)
            .where(Batch.expiry_date >= today).group_by(Batch.item_id).subquery()
        )
        out.below_par_items = int(await db.scalar(
            select(func.count()).select_from(Item).outerjoin(on_hand, on_hand.c.item_id == Item.id)
            .where(Item.is_active, Item.par_min > 0, func.coalesce(on_hand.c.oh, 0) < Item.par_min)
        ) or 0)
    loc = await pharmacy.pharmacy_location(db)
    if p.has("pharmacy_order:view", loc.id):
        start = datetime.combine(today, datetime.min.time()).replace(tzinfo=UTC)
        in_loc = PharmacyOrder.location_id == loc.id
        out.orders_awaiting_dispatch = int(await db.scalar(select(func.count()).select_from(PharmacyOrder).where(
            in_loc, PharmacyOrder.status == OrderStatus.allocated)) or 0)
        out.counter_sales_today = Decimal(await db.scalar(select(func.coalesce(func.sum(PharmacyOrder.total), 0)).where(
            in_loc, PharmacyOrder.channel == OrderChannel.counter_sale,
            PharmacyOrder.status.in_([OrderStatus.dispatched, OrderStatus.partially_returned]),
            PharmacyOrder.dispatched_at >= start, PharmacyOrder.dispatched_at < start + timedelta(days=1))) or 0)
        out.requisitions_today = int(await db.scalar(select(func.count()).select_from(PharmacyOrder).where(
            in_loc, PharmacyOrder.channel == OrderChannel.requisition, PharmacyOrder.created_at >= start)) or 0)
    return out
