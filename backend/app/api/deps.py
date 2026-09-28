from collections.abc import Callable, Coroutine
from typing import Annotated, Any

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import forbidden
from app.core.rbac import Principal, load_grants, resolve_user
from app.core.security import AuthError, TokenValidator
from app.db.session import get_db

_bearer = HTTPBearer(auto_error=False)
_validator: TokenValidator | None = None


def get_validator() -> TokenValidator:
    global _validator
    if _validator is None:
        _validator = TokenValidator(get_settings())
    return _validator


DB = Annotated[AsyncSession, Depends(get_db)]


async def get_principal(
    request: Request,
    db: DB,
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    validator: TokenValidator = Depends(get_validator),
) -> Principal:
    if creds is None or creds.scheme.lower() != "bearer":
        raise AuthError("MISSING_TOKEN", "Authorization bearer token is required")
    ident = validator.validate(creds.credentials)
    user = await resolve_user(db, ident, get_settings())
    return Principal(
        user_id=user.id,
        email=user.email,
        display_name=user.display_name,
        grants=await load_grants(db, user.id),
        request_id=getattr(request.state, "request_id", None),
        ip=request.client.host if request.client else None,
    )


CurrentPrincipal = Annotated[Principal, Depends(get_principal)]


def require(*perms: str, any_of: bool = False) -> Callable[..., Coroutine[Any, Any, Principal]]:
    """Dependency: principal must hold all (or any, with any_of=True) of `perms` at some location."""

    async def dep(p: CurrentPrincipal) -> Principal:
        ok = any(p.has(x) for x in perms) if any_of else all(p.has(x) for x in perms)
        if not ok:
            missing = [x for x in perms if not p.has(x)]
            raise forbidden(missing=missing)
        return p

    dep.__rbac_permissions__ = (perms, any_of)  # type: ignore[attr-defined]  # introspected by tests
    return dep
