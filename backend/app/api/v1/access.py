import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select

from app.api.deps import DB, require
from app.core.rbac import Principal
from app.models import Permission, UserStatus
from app.schemas.common import Page
from app.schemas.identity import (
    PermissionOut,
    RoleCreate,
    RoleOut,
    RolePermissionsUpdate,
    RoleUpdate,
    StaffCreate,
    StaffOut,
    StaffRolesUpdate,
    StaffUpdate,
)
from app.services import access

router = APIRouter(tags=["staff & roles"])


@router.get("/staff", response_model=Page[StaffOut])
async def list_staff(
    db: DB,
    p: Principal = Depends(require("staff:view")),
    q: str | None = None,
    status_: UserStatus | None = Query(None, alias="status"),
    role_id: uuid.UUID | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
) -> Page[StaffOut]:
    users, total = await access.list_staff(db, q=q, status=status_, role_id=role_id, page=page, page_size=page_size)
    return Page(items=[access.staff_out(u) for u in users], total=total, page=page, page_size=page_size)


@router.post("/staff", response_model=StaffOut, status_code=status.HTTP_201_CREATED)
async def invite_staff(body: StaffCreate, db: DB, p: Principal = Depends(require("staff:manage"))) -> StaffOut:
    return access.staff_out(await access.invite_staff(db, p, body))


@router.get("/staff/{user_id}", response_model=StaffOut)
async def get_staff(user_id: uuid.UUID, db: DB, p: Principal = Depends(require("staff:view"))) -> StaffOut:
    return access.staff_out(await access.get_staff(db, user_id))


@router.patch("/staff/{user_id}", response_model=StaffOut)
async def update_staff(
    user_id: uuid.UUID, body: StaffUpdate, db: DB, p: Principal = Depends(require("staff:manage"))
) -> StaffOut:
    return access.staff_out(await access.update_staff(db, p, user_id, body))


@router.put("/staff/{user_id}/roles", response_model=StaffOut)
async def set_staff_roles(
    user_id: uuid.UUID, body: StaffRolesUpdate, db: DB, p: Principal = Depends(require("staff:manage"))
) -> StaffOut:
    return access.staff_out(await access.set_staff_roles(db, p, user_id, body.roles))


@router.post("/staff/{user_id}/deactivate", response_model=StaffOut)
async def deactivate_staff(user_id: uuid.UUID, db: DB, p: Principal = Depends(require("staff:manage"))) -> StaffOut:
    return access.staff_out(await access.set_staff_status(db, p, user_id, active=False))


@router.post("/staff/{user_id}/reactivate", response_model=StaffOut)
async def reactivate_staff(user_id: uuid.UUID, db: DB, p: Principal = Depends(require("staff:manage"))) -> StaffOut:
    return access.staff_out(await access.set_staff_status(db, p, user_id, active=True))


@router.get("/permissions", response_model=list[PermissionOut])
async def list_permissions(
    db: DB, p: Principal = Depends(require("staff:view", "role:manage", any_of=True))
) -> list[Permission]:
    return list((await db.scalars(select(Permission).order_by(Permission.module, Permission.code))).all())


@router.get("/roles", response_model=list[RoleOut])
async def list_roles(
    db: DB, p: Principal = Depends(require("staff:view", "role:manage", any_of=True))
) -> list[RoleOut]:
    return await access.list_roles(db)


@router.post("/roles", response_model=RoleOut, status_code=status.HTTP_201_CREATED)
async def create_role(body: RoleCreate, db: DB, p: Principal = Depends(require("role:manage"))) -> RoleOut:
    r = await access.create_role(db, p, body)
    return await access.role_out(db, r.id)


@router.patch("/roles/{role_id}", response_model=RoleOut)
async def update_role(
    role_id: uuid.UUID, body: RoleUpdate, db: DB, p: Principal = Depends(require("role:manage"))
) -> RoleOut:
    await access.update_role(db, p, role_id, body)
    return await access.role_out(db, role_id)


@router.put("/roles/{role_id}/permissions", response_model=RoleOut)
async def set_role_permissions(
    role_id: uuid.UUID, body: RolePermissionsUpdate, db: DB, p: Principal = Depends(require("role:manage"))
) -> RoleOut:
    await access.set_role_permissions(db, p, role_id, body.permissions)
    return await access.role_out(db, role_id)


@router.delete("/roles/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_role(role_id: uuid.UUID, db: DB, p: Principal = Depends(require("role:manage"))) -> None:
    await access.delete_role(db, p, role_id)
