from fastapi import APIRouter
from pydantic import BaseModel, EmailStr
from sqlalchemy import func, select

from app.api.deps import DB, CurrentPrincipal
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.security import mint_dev_token
from app.models import Location, User, UserStatus
from app.schemas.identity import LocationOut, MeOut
from app.services.access import get_staff, list_staff, staff_out

router = APIRouter(tags=["auth"])


@router.get("/me", response_model=MeOut)
async def me(p: CurrentPrincipal, db: DB) -> MeOut:
    user = await get_staff(db, p.user_id)
    locations = (await db.scalars(select(Location).where(Location.is_active).order_by(Location.name))).all()
    return MeOut(
        user=staff_out(user),
        permissions=sorted(p.permissions),
        permission_scopes={k: sorted(v, key=lambda x: str(x) if x else "") for k, v in p.grants.items()},
        locations=[LocationOut.model_validate(loc) for loc in locations],
    )


@router.get("/locations", response_model=list[LocationOut])
async def locations(p: CurrentPrincipal, db: DB) -> list[Location]:
    return list((await db.scalars(select(Location).where(Location.is_active).order_by(Location.name))).all())


# ----------------------------------------------------------------------------- dev-only sign-in
dev_router = APIRouter(prefix="/dev", tags=["dev"])


class DevUser(BaseModel):
    email: str
    display_name: str
    job_title: str | None
    roles: list[str]


class DevTokenIn(BaseModel):
    email: EmailStr


class DevTokenOut(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    expires_in: int


def _dev_only() -> None:
    if get_settings().auth_mode != "dev":
        raise AppError(404, "NOT_FOUND", "Not found")


@dev_router.get("/users", response_model=list[DevUser])
async def dev_users(db: DB) -> list[DevUser]:
    """Seeded accounts for the local sign-in picker (AUTH_MODE=dev only)."""
    _dev_only()
    users, _ = await list_staff(
        db, q=None, status=None, role_id=None, page=1, page_size=100)
    return [
        DevUser(email=u.email, display_name=u.display_name, job_title=u.job_title,
                roles=sorted({a.role.name for a in u.role_assignments}))
        for u in users if u.status != UserStatus.inactive
    ]


@dev_router.post("/token", response_model=DevTokenOut)
async def dev_token(body: DevTokenIn, db: DB) -> DevTokenOut:
    """Mint a local token that mimics an Entra access token (AUTH_MODE=dev only)."""
    _dev_only()
    email = body.email.lower()
    user = await db.scalar(select(User).where(func.lower(User.email) == email))
    # A stable fake Entra object id per email; unknown emails get a token too so the
    # "not provisioned" path can be exercised locally.
    oid = user.oid if user and user.oid else f"dev-{email}"
    name = user.display_name if user else email
    ttl = 8 * 3600
    return DevTokenOut(access_token=mint_dev_token(oid=oid, email=email, name=name, ttl=ttl), expires_in=ttl)
