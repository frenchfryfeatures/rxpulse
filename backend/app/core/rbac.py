import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError, forbidden
from app.core.permissions import SUPER_ADMIN
from app.core.security import TokenIdentity
from app.models import Role, RolePermission, User, UserRole, UserStatus

GLOBAL = None  # location scope meaning "every location"


@dataclass
class Principal:
    user_id: uuid.UUID
    email: str
    display_name: str
    # permission -> set of location ids it applies to (None = every location)
    grants: dict[str, set[uuid.UUID | None]] = field(default_factory=dict)
    request_id: str | None = None
    ip: str | None = None

    @property
    def permissions(self) -> frozenset[str]:
        return frozenset(self.grants)

    def has(self, perm: str, location_id: uuid.UUID | None = None) -> bool:
        scopes = self.grants.get(perm)
        if not scopes:
            return False
        if location_id is None:
            return True
        return GLOBAL in scopes or location_id in scopes

    def locations_for(self, perm: str) -> set[uuid.UUID] | None:
        """None = all locations; empty set = none."""
        scopes = self.grants.get(perm, set())
        if GLOBAL in scopes:
            return None
        return {s for s in scopes if s is not None}


async def load_grants(db: AsyncSession, user_id: uuid.UUID) -> dict[str, set[uuid.UUID | None]]:
    rows = await db.execute(
        select(RolePermission.permission_code, UserRole.location_id)
        .join(UserRole, UserRole.role_id == RolePermission.role_id)
        .where(UserRole.user_id == user_id)
    )
    grants: dict[str, set[uuid.UUID | None]] = defaultdict(set)
    for code, loc in rows:
        grants[code].add(loc)
    return dict(grants)


async def resolve_user(db: AsyncSession, ident: TokenIdentity, settings: Settings) -> User:
    """Map a validated token to an active RxPulse user (JIT-linking invitations)."""
    user = await db.scalar(select(User).where(User.tid == ident.tid, User.oid == ident.oid))
    is_break_glass = settings.super_admin_app_role in ident.app_roles
    now = datetime.now(UTC)

    if user is None and ident.email:
        invited = await db.scalar(
            select(User).where(func.lower(User.email) == ident.email, User.oid.is_(None))
        )
        if invited is not None:
            invited.oid, invited.tid = ident.oid, ident.tid
            if invited.status == UserStatus.invited:
                invited.status = UserStatus.active
            user = invited

    if user is None and is_break_glass:
        user = User(
            oid=ident.oid, tid=ident.tid, email=ident.email or f"{ident.oid}@unknown",
            display_name=ident.name or ident.email or "Administrator", status=UserStatus.active,
        )
        db.add(user)
        await db.flush()

    if user is None:
        raise AppError(403, "ACCOUNT_NOT_PROVISIONED",
                       "Your account has not been added to RxPulse. Please contact your administrator.")
    if user.status == UserStatus.inactive:
        raise AppError(403, "ACCOUNT_DEACTIVATED",
                       "Your RxPulse account has been deactivated. Please contact your administrator.")

    if is_break_glass:
        sa = await db.scalar(select(Role).where(Role.name == SUPER_ADMIN))
        if sa is not None:
            has = await db.scalar(select(UserRole.id).where(
                UserRole.user_id == user.id, UserRole.role_id == sa.id, UserRole.location_id.is_(None)))
            if has is None:
                db.add(UserRole(user_id=user.id, role_id=sa.id, location_id=None))

    if ident.name and user.display_name in (None, "", user.email):
        user.display_name = ident.name
    if user.last_login_at is None or now - user.last_login_at > timedelta(minutes=5):
        user.last_login_at = now
    if db.new or db.dirty:
        await db.commit()
    return user


def ensure(p: Principal, perm: str, location_id: uuid.UUID | None = None) -> None:
    if not p.has(perm, location_id):
        raise forbidden(missing=[perm])
