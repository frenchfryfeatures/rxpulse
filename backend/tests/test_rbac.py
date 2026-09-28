"""Route × role authorization matrix.

1. Every API route must be protected: either by a `require(...)` dependency or by being listed in
   SELF_CHECKED (routes that authorize inside the service, with their own tests).
2. For a representative set of routes, each seeded role gets exactly the expected outcome.
"""

import pytest
from fastapi.routing import APIRoute

from app.core.permissions import ALL_PERMISSIONS, DEFAULT_ROLES
from app.main import app
from tests.conftest import (
    ADMIN,
    ANALYST,
    BILLING,
    HOSP_ADMIN,
    NURSE,
    PHARMACIST,
    PROCURE,
    RETINA,
    STORE,
    SURGEON,
)

PUBLIC = {"/health", "/api/v1/dev/users", "/api/v1/dev/token"}
# Authenticated routes whose authorization is enforced in the service layer (tested in test_pharmacy.py etc.)
SELF_CHECKED = {
    ("GET", "/api/v1/me"), ("GET", "/api/v1/locations"), ("GET", "/api/v1/dashboard/summary"),
    ("GET", "/api/v1/pharmacy/orders"), ("POST", "/api/v1/pharmacy/orders"),
    ("GET", "/api/v1/pharmacy/orders/{order_id}"), ("GET", "/api/v1/pharmacy/orders/{order_id}/pick-list"),
    ("POST", "/api/v1/pharmacy/orders/{order_id}/cancel"),
}


def _routes():
    """Yield (full_path, APIRoute) for every API route, including those in included routers."""
    for r in app.router.routes:
        if isinstance(r, APIRoute):
            yield r.path_format, r
        original = getattr(r, "original_router", None)  # FastAPI's lazily included routers
        if original is not None:
            for sub in original.routes:
                if isinstance(sub, APIRoute):
                    yield "/api/v1" + sub.path_format, sub


def _has_require(route: APIRoute) -> bool:
    stack = list(route.dependant.dependencies)
    while stack:
        d = stack.pop()
        if getattr(d.call, "__rbac_permissions__", None):
            return True
        stack.extend(d.dependencies)
    return False


def test_every_route_is_protected():
    paths = app.openapi()["paths"]
    unprotected = []
    seen = 0
    for path, ops in paths.items():
        for method in ops:
            seen += 1
            if path in PUBLIC or (method.upper(), path) in SELF_CHECKED:
                continue
            route = next((r for p, r in _routes() if p == path and method.upper() in r.methods), None)
            assert route is not None, f"route not found for {method} {path}"
            if not _has_require(route):
                unprotected.append(f"{method.upper()} {path}")
    assert seen > 30
    assert not unprotected, f"Routes without a require() dependency: {unprotected}"


def test_super_admin_holds_every_permission_and_roles_only_use_known_permissions():
    sa = next(r for r in DEFAULT_ROLES if r.immutable)
    assert sa.permissions == ALL_PERMISSIONS
    for r in DEFAULT_ROLES:
        assert r.permissions <= ALL_PERMISSIONS


ALL_ROLES = [ADMIN, HOSP_ADMIN, SURGEON, PHARMACIST, NURSE, STORE, PROCURE, BILLING, ANALYST]
# route -> users allowed (everyone else must get 403)
MATRIX = {
    ("GET", "/staff"): {ADMIN, HOSP_ADMIN},
    ("GET", "/roles"): {ADMIN, HOSP_ADMIN},
    ("GET", "/audit"): {ADMIN, HOSP_ADMIN},
    ("GET", "/batches"): {ADMIN, HOSP_ADMIN, PHARMACIST, STORE, PROCURE, ANALYST},
    ("GET", "/stock/expiry-risk"): {ADMIN, HOSP_ADMIN, PHARMACIST, STORE, PROCURE, ANALYST},
    ("GET", "/items"): {ADMIN, HOSP_ADMIN, PHARMACIST, STORE, PROCURE, ANALYST, SURGEON, NURSE},
    ("GET", "/pharmacy/orders"): {ADMIN, HOSP_ADMIN, PHARMACIST, BILLING, ANALYST, SURGEON, NURSE},
    ("GET", "/patients?q=ra"): {ADMIN, HOSP_ADMIN, PHARMACIST},
}


@pytest.mark.parametrize("route", list(MATRIX), ids=lambda r: f"{r[0]} {r[1]}")
async def test_role_matrix(api, route):
    method, path = route
    allowed = MATRIX[route]
    for who in ALL_ROLES:
        async with api.as_(who) as c:
            r = await c.request(method, path)
        expected = 200 if who in allowed else 403
        assert r.status_code == expected, f"{who} {method} {path}: {r.status_code} {r.text[:200]}"


async def test_writes_matrix(api, db):
    # Only role:manage holders may create roles: Hospital Admin deliberately lacks it.
    for who, expected in [(ADMIN, 201), (HOSP_ADMIN, 403), (PHARMACIST, 403)]:
        async with api.as_(who) as c:
            r = await c.post("/roles", json={"name": f"Temp {who}", "permissions": ["inventory:view"]})
        assert r.status_code == expected, (who, r.text)


async def test_location_scoping_limits_batches(api):
    # The pharmacist is scoped to Main Pharmacy and must not see Central Store / OT Store stock.
    async with api.as_(PHARMACIST) as c:
        rows = (await c.get("/batches", params={"page_size": 100})).json()["items"]
    assert rows and {r["location_name"] for r in rows} == {"Main Pharmacy"}
    async with api.as_(RETINA) as c:  # doctors have no inventory:view at all
        assert (await c.get("/batches")).status_code == 403
