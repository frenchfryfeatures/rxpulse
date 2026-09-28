import uuid
from datetime import date, datetime, time, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, or_, select

from app.api.deps import DB, CurrentPrincipal, require
from app.core.errors import conflict
from app.core.rbac import Principal
from app.models import OrderChannel, OrderStatus, Patient, PharmacyOrder, RolePermission, User, UserRole, UserStatus
from app.schemas.common import Page
from app.schemas.pharmacy import OrderCreate, OrderOut, PatientIn, PatientOut, PickListOut, ReturnIn
from app.services import audit, pharmacy

router = APIRouter(tags=["pharmacy"])


# ----------------------------------------------------------------------------- patients
@router.get("/patients", response_model=list[PatientOut])
async def search_patients(
    db: DB, q: str = Query(min_length=2),
    p: Principal = Depends(require("pharmacy_order:create", "patient:manage", any_of=True)),
) -> list[Patient]:
    like = f"%{q.lower()}%"
    stmt = select(Patient).where(or_(func.lower(Patient.name).like(like), func.lower(Patient.mrn).like(like),
                                     Patient.phone.like(like))).order_by(Patient.name).limit(20)
    return list((await db.scalars(stmt)).all())


@router.post("/patients", response_model=PatientOut, status_code=status.HTTP_201_CREATED)
async def create_patient(body: PatientIn, db: DB, p: Principal = Depends(require("patient:manage"))) -> Patient:
    if await db.scalar(select(Patient.id).where(func.lower(Patient.mrn) == body.mrn.lower())):
        raise conflict("MRN_EXISTS", "A patient with this MRN already exists")
    pt = Patient(**body.model_dump())
    db.add(pt)
    await db.flush()
    await audit.record(db, p, "patient.create", "patient", pt.id, after={"mrn": pt.mrn})
    await db.commit()
    return pt


# ----------------------------------------------------------------------------- orders
_SORTS = {
    "date_desc": PharmacyOrder.created_at.desc(), "date_asc": PharmacyOrder.created_at.asc(),
    "total_desc": PharmacyOrder.total.desc(), "total_asc": PharmacyOrder.total.asc(),
}


@router.get("/pharmacy/orders", response_model=Page[OrderOut])
async def list_orders(
    p: CurrentPrincipal, db: DB,
    channel: OrderChannel | None = None,
    status_: OrderStatus | None = Query(None, alias="status"),
    q: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    sort: Literal["date_desc", "date_asc", "total_desc", "total_asc"] = "date_desc",
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
) -> Page[OrderOut]:
    loc = await pharmacy.pharmacy_location(db)
    stmt = pharmacy.scope_orders(select(PharmacyOrder), p, loc)
    if channel:
        stmt = stmt.where(PharmacyOrder.channel == channel)
    if status_:
        stmt = stmt.where(PharmacyOrder.status == status_)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.outerjoin(Patient, Patient.id == PharmacyOrder.patient_id).outerjoin(
            User, User.id == PharmacyOrder.requested_by_id
        ).where(or_(
            func.lower(PharmacyOrder.order_no).like(like), func.lower(PharmacyOrder.invoice_no).like(like),
            func.lower(PharmacyOrder.walk_in_name).like(like), func.lower(Patient.name).like(like),
            func.lower(Patient.mrn).like(like), func.lower(User.display_name).like(like),
            func.lower(PharmacyOrder.department).like(like),
        ))
    if date_from:
        stmt = stmt.where(PharmacyOrder.created_at >= datetime.combine(date_from, time.min))
    if date_to:
        stmt = stmt.where(PharmacyOrder.created_at < datetime.combine(date_to + timedelta(days=1), time.min))
    total = await pharmacy.count_orders(db, stmt)
    ids = (await db.scalars(stmt.with_only_columns(PharmacyOrder.id).order_by(_SORTS[sort], PharmacyOrder.id)
                            .offset((page - 1) * page_size).limit(page_size))).all()
    orders = {o.id: o for o in (await db.scalars(
        select(PharmacyOrder).where(PharmacyOrder.id.in_(ids)).options(*pharmacy._order_opts))).all()}
    return Page(items=[pharmacy.order_out(orders[i]) for i in ids], total=total, page=page, page_size=page_size)


@router.post("/pharmacy/orders", response_model=OrderOut, status_code=status.HTTP_201_CREATED)
async def create_order(body: OrderCreate, p: CurrentPrincipal, db: DB) -> OrderOut:
    return pharmacy.order_out(await pharmacy.create_order(db, p, body))


@router.get("/pharmacy/orders/{order_id}", response_model=OrderOut)
async def get_order(order_id: uuid.UUID, p: CurrentPrincipal, db: DB) -> OrderOut:
    o = await pharmacy.get_order(db, order_id)
    pharmacy.ensure_can_view(p, o)
    return pharmacy.order_out(o)


@router.get("/pharmacy/orders/{order_id}/pick-list", response_model=PickListOut)
async def pick_list(order_id: uuid.UUID, p: CurrentPrincipal, db: DB) -> PickListOut:
    o = await pharmacy.get_order(db, order_id)
    pharmacy.ensure_can_view(p, o)
    return await pharmacy.pick_list(db, o)


@router.post("/pharmacy/orders/{order_id}/dispatch", response_model=OrderOut)
async def dispatch(order_id: uuid.UUID, db: DB,
                   p: Principal = Depends(require("pharmacy_order:dispatch"))) -> OrderOut:
    return pharmacy.order_out(await pharmacy.dispatch(db, p, order_id))


@router.post("/pharmacy/orders/{order_id}/cancel", response_model=OrderOut)
async def cancel(order_id: uuid.UUID, p: CurrentPrincipal, db: DB) -> OrderOut:
    return pharmacy.order_out(await pharmacy.cancel(db, p, order_id))


@router.post("/pharmacy/orders/{order_id}/return", response_model=OrderOut)
async def return_items(order_id: uuid.UUID, body: ReturnIn, db: DB,
                       p: Principal = Depends(require("pharmacy_order:return"))) -> OrderOut:
    return pharmacy.order_out(await pharmacy.return_items(db, p, order_id, body))


@router.get("/pharmacy/requesters", response_model=list[dict])
async def requesters(db: DB, p: Principal = Depends(require("pharmacy_order:create"))) -> list[dict]:
    """Active staff who can raise requisitions (for the pharmacist's 'on behalf of' picker)."""
    rows = (await db.execute(
        select(User.id, User.display_name, User.department).distinct()
        .join(UserRole, UserRole.user_id == User.id)
        .join(RolePermission, RolePermission.role_id == UserRole.role_id)
        .where(RolePermission.permission_code == "requisition:create", User.status == UserStatus.active)
        .order_by(User.display_name)
    )).all()
    return [{"id": str(i), "display_name": n, "department": d} for i, n, d in rows]
