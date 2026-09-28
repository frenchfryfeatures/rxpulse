"""Staff accounts and roles.

Rules enforced here (not only in the UI):
- You can only grant permissions you hold yourself (no privilege escalation), whether by
  assigning a role or by editing a role's permissions.
- You cannot change your own role assignments or deactivate yourself.
- There must always be at least one active Super Admin.
- Super Admin is immutable; other system roles can have permissions edited but can't be renamed or deleted.
"""

import uuid
from collections import defaultdict

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import AppError, conflict, forbidden, not_found
from app.core.permissions import ALL_PERMISSIONS, CATALOGUE, DEFAULT_ROLES, SUPER_ADMIN
from app.core.rbac import Principal
from app.models import Location, Permission, Role, RolePermission, User, UserRole, UserStatus
from app.schemas.identity import (
    RoleAssignmentIn,
    RoleAssignmentOut,
    RoleCreate,
    RoleOut,
    RoleUpdate,
    StaffCreate,
    StaffOut,
    StaffUpdate,
)
from app.services import audit


# ----------------------------------------------------------------------------- catalogue sync
async def sync_catalogue(db: AsyncSession) -> None:
    """Upsert permissions and system roles from app.core.permissions (idempotent)."""
    existing = {p.code: p for p in (await db.scalars(select(Permission))).all()}
    for module, perms in CATALOGUE.items():
        for code, desc in perms:
            if code in existing:
                existing[code].module, existing[code].description = module, desc
            else:
                db.add(Permission(code=code, module=module, description=desc))
    for code, perm in existing.items():
        if code not in ALL_PERMISSIONS:
            await db.delete(perm)
    await db.flush()

    for rd in DEFAULT_ROLES:
        role = await db.scalar(select(Role).where(Role.name == rd.name).options(selectinload(Role.permissions)))
        if role is None:
            role = Role(name=rd.name, description=rd.description, is_system=True, is_immutable=rd.immutable)
            role.permissions = [RolePermission(permission_code=c) for c in sorted(rd.permissions)]
            db.add(role)
        elif rd.immutable:
            # Super Admin always holds every permission, including newly added ones.
            have = {rp.permission_code for rp in role.permissions}
            for c in sorted(rd.permissions - have):
                role.permissions.append(RolePermission(permission_code=c))
    await db.commit()


# ----------------------------------------------------------------------------- helpers
def _check_can_grant(actor: Principal, perms: set[str]) -> None:
    missing = sorted(p for p in perms if not actor.has(p))
    if missing:
        raise forbidden("You can only grant permissions that you hold yourself", missing=missing)


async def _role_perms(db: AsyncSession, role_ids: set[uuid.UUID]) -> dict[uuid.UUID, set[str]]:
    out: dict[uuid.UUID, set[str]] = defaultdict(set)
    rows = await db.execute(
        select(RolePermission.role_id, RolePermission.permission_code).where(RolePermission.role_id.in_(role_ids))
    )
    for rid, code in rows:
        out[rid].add(code)
    return out


async def _super_admin_role(db: AsyncSession) -> Role:
    role = await db.scalar(select(Role).where(Role.name == SUPER_ADMIN))
    assert role is not None, "catalogue not synced"
    return role


async def _active_super_admins(db: AsyncSession, exclude_user: uuid.UUID | None = None) -> int:
    sa = await _super_admin_role(db)
    q = (
        select(func.count(func.distinct(User.id)))
        .join(UserRole, UserRole.user_id == User.id)
        .where(UserRole.role_id == sa.id, UserRole.location_id.is_(None), User.status != UserStatus.inactive)
    )
    if exclude_user:
        q = q.where(User.id != exclude_user)
    return int(await db.scalar(q) or 0)


def staff_out(u: User) -> StaffOut:
    return StaffOut(
        id=u.id, email=u.email, display_name=u.display_name, job_title=u.job_title, department=u.department,
        status=u.status, last_login_at=u.last_login_at, linked=u.oid is not None,
        roles=[
            RoleAssignmentOut(
                role_id=a.role_id, role_name=a.role.name, location_id=a.location_id,
                location_name=a.location.name if a.location else None,
            )
            for a in sorted(u.role_assignments, key=lambda a: a.role.name)
        ],
    )


def _staff_snapshot(u: User) -> dict:
    return {
        "email": u.email, "display_name": u.display_name, "job_title": u.job_title, "department": u.department,
        "status": u.status.value,
        "roles": sorted(f"{a.role_id}@{a.location_id or '*'}" for a in u.role_assignments),
    }


_staff_opts = (selectinload(User.role_assignments).selectinload(UserRole.role),
               selectinload(User.role_assignments).selectinload(UserRole.location))


async def get_staff(db: AsyncSession, user_id: uuid.UUID) -> User:
    u = await db.scalar(select(User).where(User.id == user_id).options(*_staff_opts))
    if u is None:
        raise not_found("Staff member")
    return u


# ----------------------------------------------------------------------------- staff
async def list_staff(
    db: AsyncSession, *, q: str | None, status: UserStatus | None, role_id: uuid.UUID | None, page: int, page_size: int
) -> tuple[list[User], int]:
    stmt = select(User)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(func.lower(User.display_name).like(like) | func.lower(User.email).like(like))
    if status:
        stmt = stmt.where(User.status == status)
    if role_id:
        stmt = stmt.where(User.id.in_(select(UserRole.user_id).where(UserRole.role_id == role_id)))
    total = int(await db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    rows = await db.scalars(
        stmt.options(*_staff_opts).order_by(User.display_name).offset((page - 1) * page_size).limit(page_size)
    )
    return list(rows.all()), total


async def _validate_assignments(db: AsyncSession, actor: Principal, roles: list[RoleAssignmentIn]) -> None:
    role_ids = {r.role_id for r in roles}
    found = set((await db.scalars(select(Role.id).where(Role.id.in_(role_ids)))).all())
    if found != role_ids:
        raise AppError(422, "VALIDATION_ERROR", "One or more roles do not exist")
    loc_ids = {r.location_id for r in roles if r.location_id}
    if loc_ids:
        found_l = set((await db.scalars(select(Location.id).where(Location.id.in_(loc_ids)))).all())
        if found_l != loc_ids:
            raise AppError(422, "VALIDATION_ERROR", "One or more locations do not exist")
    keys = [(r.role_id, r.location_id) for r in roles]
    if len(keys) != len(set(keys)):
        raise AppError(422, "VALIDATION_ERROR", "Duplicate role assignment")
    perms = await _role_perms(db, role_ids)
    _check_can_grant(actor, set().union(*perms.values()) if perms else set())


async def invite_staff(db: AsyncSession, actor: Principal, data: StaffCreate) -> User:
    email = data.email.lower()
    if await db.scalar(select(User.id).where(func.lower(User.email) == email)):
        raise conflict("EMAIL_EXISTS", "A staff member with this email already exists")
    await _validate_assignments(db, actor, data.roles)
    u = User(
        email=email, display_name=data.display_name, job_title=data.job_title, department=data.department,
        status=UserStatus.invited, invited_by_id=actor.user_id,
    )
    u.role_assignments = [
        UserRole(role_id=r.role_id, location_id=r.location_id, assigned_by_id=actor.user_id) for r in data.roles
    ]
    db.add(u)
    await db.flush()
    u = await get_staff(db, u.id)
    await audit.record(db, actor, "staff.invite", "user", u.id, after=_staff_snapshot(u))
    await db.commit()
    return u


async def update_staff(db: AsyncSession, actor: Principal, user_id: uuid.UUID, data: StaffUpdate) -> User:
    u = await get_staff(db, user_id)
    before = _staff_snapshot(u)
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(u, k, v)
    await audit.record(db, actor, "staff.update", "user", u.id, before=before, after=_staff_snapshot(u))
    await db.commit()
    return await get_staff(db, user_id)


async def set_staff_roles(
    db: AsyncSession, actor: Principal, user_id: uuid.UUID, roles: list[RoleAssignmentIn]
) -> User:
    if user_id == actor.user_id:
        raise forbidden("You cannot change your own roles. Ask another administrator.")
    u = await get_staff(db, user_id)
    before = _staff_snapshot(u)
    await _validate_assignments(db, actor, roles)
    # Removing roles is also privileged: you may only remove roles whose permissions you hold.
    removed = {a.role_id for a in u.role_assignments} - {r.role_id for r in roles}
    if removed:
        rp = await _role_perms(db, removed)
        _check_can_grant(actor, set().union(*rp.values()) if rp else set())
    sa = await _super_admin_role(db)
    keeps_sa = any(r.role_id == sa.id and r.location_id is None for r in roles)
    if not keeps_sa and u.status != UserStatus.inactive and await _active_super_admins(db, exclude_user=u.id) == 0:
        was_sa = any(a.role_id == sa.id and a.location_id is None for a in u.role_assignments)
        if was_sa:
            raise conflict("LAST_SUPER_ADMIN", "At least one active Super Admin must remain")
    u.role_assignments.clear()
    await db.flush()
    for r in roles:
        u.role_assignments.append(
            UserRole(role_id=r.role_id, location_id=r.location_id, assigned_by_id=actor.user_id)
        )
    await db.flush()
    db.expire(u)
    u = await get_staff(db, user_id)
    await audit.record(db, actor, "staff.roles", "user", u.id, before=before, after=_staff_snapshot(u))
    await db.commit()
    return u


async def set_staff_status(db: AsyncSession, actor: Principal, user_id: uuid.UUID, active: bool) -> User:
    u = await get_staff(db, user_id)
    before = _staff_snapshot(u)
    if not active:
        if user_id == actor.user_id:
            raise forbidden("You cannot deactivate your own account")
        if u.status == UserStatus.inactive:
            return u
        sa = await _super_admin_role(db)
        if any(a.role_id == sa.id and a.location_id is None for a in u.role_assignments):
            if await _active_super_admins(db, exclude_user=u.id) == 0:
                raise conflict("LAST_SUPER_ADMIN", "The last active Super Admin cannot be deactivated")
        # Deactivating someone with more power than you would be a privilege problem too.
        rp = await _role_perms(db, {a.role_id for a in u.role_assignments})
        _check_can_grant(actor, set().union(*rp.values()) if rp else set())
        u.status = UserStatus.inactive
    else:
        if u.status != UserStatus.inactive:
            return u
        u.status = UserStatus.active if u.oid else UserStatus.invited
    await audit.record(db, actor, "staff.activate" if active else "staff.deactivate", "user", u.id,
                       before=before, after=_staff_snapshot(u))
    await db.commit()
    return u


# ----------------------------------------------------------------------------- roles
async def list_roles(db: AsyncSession) -> list[RoleOut]:
    roles = (await db.scalars(select(Role).options(selectinload(Role.permissions)).order_by(
        Role.is_system.desc(), Role.name))).all()
    counts = dict((await db.execute(
        select(UserRole.role_id, func.count(func.distinct(UserRole.user_id)))
        .join(User, User.id == UserRole.user_id)
        .where(User.status != UserStatus.inactive)
        .group_by(UserRole.role_id)
    )).all())
    return [_role_out(r, counts.get(r.id, 0)) for r in roles]


def _role_out(r: Role, user_count: int) -> RoleOut:
    perms = sorted(p.permission_code for p in r.permissions)
    return RoleOut(
        id=r.id, name=r.name, description=r.description, is_system=r.is_system, is_immutable=r.is_immutable,
        permissions=perms, permission_count=len(perms), user_count=user_count,
    )


async def get_role(db: AsyncSession, role_id: uuid.UUID) -> Role:
    r = await db.scalar(select(Role).where(Role.id == role_id).options(selectinload(Role.permissions)))
    if r is None:
        raise not_found("Role")
    return r


async def role_out(db: AsyncSession, role_id: uuid.UUID) -> RoleOut:
    return next(r for r in await list_roles(db) if r.id == role_id)


def _validate_perm_codes(perms: list[str]) -> set[str]:
    unknown = sorted(set(perms) - ALL_PERMISSIONS)
    if unknown:
        raise AppError(422, "VALIDATION_ERROR", f"Unknown permissions: {', '.join(unknown)}")
    return set(perms)


async def create_role(db: AsyncSession, actor: Principal, data: RoleCreate) -> Role:
    if await db.scalar(select(Role.id).where(func.lower(Role.name) == data.name.strip().lower())):
        raise conflict("ROLE_EXISTS", "A role with this name already exists")
    perms = _validate_perm_codes(data.permissions)
    _check_can_grant(actor, perms)
    r = Role(name=data.name.strip(), description=data.description, is_system=False)
    r.permissions = [RolePermission(permission_code=c) for c in sorted(perms)]
    db.add(r)
    await db.flush()
    await audit.record(db, actor, "role.create", "role", r.id,
                       after={"name": r.name, "permissions": sorted(perms)})
    await db.commit()
    return r


async def update_role(db: AsyncSession, actor: Principal, role_id: uuid.UUID, data: RoleUpdate) -> Role:
    r = await get_role(db, role_id)
    if r.is_immutable:
        raise forbidden(f"The {r.name} role cannot be modified")
    changes = data.model_dump(exclude_unset=True)
    if "name" in changes and r.is_system and changes["name"] != r.name:
        raise forbidden("System roles cannot be renamed")
    if "name" in changes and changes["name"].strip().lower() != r.name.lower():
        if await db.scalar(select(Role.id).where(func.lower(Role.name) == changes["name"].strip().lower())):
            raise conflict("ROLE_EXISTS", "A role with this name already exists")
    before = {"name": r.name, "description": r.description}
    for k, v in changes.items():
        setattr(r, k, v.strip() if isinstance(v, str) else v)
    await audit.record(db, actor, "role.update", "role", r.id, before=before,
                       after={"name": r.name, "description": r.description})
    await db.commit()
    return r


async def set_role_permissions(db: AsyncSession, actor: Principal, role_id: uuid.UUID, perms: list[str]) -> Role:
    r = await get_role(db, role_id)
    if r.is_immutable:
        raise forbidden(f"The {r.name} role cannot be modified")
    new = _validate_perm_codes(perms)
    old = {p.permission_code for p in r.permissions}
    # Both adding and removing a permission require holding it.
    _check_can_grant(actor, new ^ old)
    if actor.user_id in set((await db.scalars(select(UserRole.user_id).where(UserRole.role_id == r.id))).all()):
        lost = {"role:manage", "staff:manage"} & (old - new)
        if lost:
            raise forbidden("You cannot remove your own administrative permissions", missing=sorted(lost))
    r.permissions = [RolePermission(permission_code=c) for c in sorted(new)]
    await audit.record(db, actor, "role.permissions", "role", r.id,
                       before={"permissions": sorted(old)}, after={"permissions": sorted(new)})
    await db.commit()
    return r


async def delete_role(db: AsyncSession, actor: Principal, role_id: uuid.UUID) -> None:
    r = await get_role(db, role_id)
    if r.is_system:
        raise forbidden("System roles cannot be deleted")
    in_use = await db.scalar(select(func.count()).select_from(UserRole).where(UserRole.role_id == r.id))
    if in_use:
        raise conflict("ROLE_IN_USE", f"This role is assigned to {in_use} staff member(s); unassign it first")
    await audit.record(db, actor, "role.delete", "role", r.id,
                       before={"name": r.name, "permissions": sorted(p.permission_code for p in r.permissions)})
    await db.delete(r)
    await db.commit()
