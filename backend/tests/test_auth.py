import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app.core.config import Settings
from app.core.security import AuthError, TokenValidator, mint_dev_token
from tests.conftest import ADMIN, INACTIVE, INVITED, PHARMACIST, email


async def test_missing_token_is_401(api):
    async with api.as_(None) as c:
        r = await c.get("/me")
    assert r.status_code == 401 and r.json()["code"] == "MISSING_TOKEN"


async def test_me_returns_permissions_and_scopes(api):
    async with api.as_(PHARMACIST) as c:
        r = await c.get("/me")
    assert r.status_code == 200
    body = r.json()
    assert body["user"]["email"] == email(PHARMACIST)
    assert "pharmacy_order:dispatch" in body["permissions"]
    assert "staff:manage" not in body["permissions"]
    # Pharmacist role is scoped to the Main Pharmacy location only
    scopes = body["permission_scopes"]["pharmacy_order:dispatch"]
    assert len(scopes) == 1 and scopes[0] is not None
    assert body["user"]["roles"][0]["location_name"] == "Main Pharmacy"


@pytest.mark.parametrize("claims,code", [
    ({"exp": int(time.time()) - 3600, "iat": int(time.time()) - 7200, "nbf": int(time.time()) - 7200},
     "TOKEN_EXPIRED"),
    ({"aud": "someone-else"}, "INVALID_TOKEN"),
    ({"iss": "https://evil.example"}, "INVALID_TOKEN"),
    ({"scp": "User.Read"}, "INSUFFICIENT_SCOPE"),
])
async def test_bad_tokens_rejected(api, claims, code):
    token = mint_dev_token(oid=f"dev-{email(ADMIN)}", email=email(ADMIN), name="x", persist=False, **claims)
    async with api.as_(None) as c:
        r = await c.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401
    assert r.json()["code"] == code


async def test_token_signed_by_other_key_rejected(api):
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = int(time.time())
    token = jwt.encode({"iss": "https://rxpulse.local/dev", "aud": "rxpulse-api-dev", "oid": "x", "tid": "t",
                        "scp": "access_as_user", "iat": now, "exp": now + 60}, other, algorithm="RS256")
    async with api.as_(None) as c:
        r = await c.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401 and r.json()["code"] == "INVALID_TOKEN"


async def test_unknown_user_not_provisioned(api):
    async with api.as_("stranger@elsewhere.example") as c:
        r = await c.get("/me")
    assert r.status_code == 403 and r.json()["code"] == "ACCOUNT_NOT_PROVISIONED"


async def test_deactivated_user_blocked_even_with_valid_token(api):
    async with api.as_(INACTIVE) as c:
        r = await c.get("/me")
    assert r.status_code == 403 and r.json()["code"] == "ACCOUNT_DEACTIVATED"


async def test_invited_user_is_linked_on_first_sign_in(api):
    async with api.as_(INVITED, oid="entra-oid-123") as c:
        r = await c.get("/me")
        assert r.status_code == 200
        assert r.json()["user"]["status"] == "active"
        assert r.json()["user"]["linked"] is True
    # A different Entra object with the same email can't hijack the now-linked account.
    async with api.as_(INVITED, oid="entra-oid-attacker") as c:
        r = await c.get("/me")
    assert r.status_code == 403 and r.json()["code"] == "ACCOUNT_NOT_PROVISIONED"


async def test_break_glass_app_role_provisions_super_admin(api):
    async with api.as_("it.admin@hospital.example", roles=["RxPulse.SuperAdmin"], name="IT Admin") as c:
        r = await c.get("/me")
    assert r.status_code == 200
    assert "role:manage" in r.json()["permissions"]
    assert [x["role_name"] for x in r.json()["user"]["roles"]] == ["Super Admin"]


# ---------------------------------------------------------------------- Entra-mode validation (mocked JWKS)
TENANT = "11111111-2222-3333-4444-555555555555"
API_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


@pytest.fixture
def entra():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    v = TokenValidator(Settings(env="test", auth_mode="entra", azure_tenant_id=TENANT, azure_api_client_id=API_ID))

    class _Key:
        def __init__(self, k):
            self.key = k

    v._jwks.get_signing_key_from_jwt = lambda token: _Key(key.public_key())  # type: ignore[union-attr]

    def make(**over):
        now = int(time.time())
        claims = {"iss": f"https://login.microsoftonline.com/{TENANT}/v2.0", "aud": API_ID, "tid": TENANT,
                  "oid": "o1", "preferred_username": "Doc@Hospital.org", "name": "Doc", "scp": "access_as_user",
                  "iat": now, "nbf": now, "exp": now + 600, **over}
        return jwt.encode(claims, key, algorithm="RS256", headers={"kid": "k1"})

    return v, make


def test_entra_valid_token(entra):
    v, make = entra
    ident = v.validate(make(roles=["RxPulse.SuperAdmin"]))
    assert ident.oid == "o1" and ident.email == "doc@hospital.org" and "RxPulse.SuperAdmin" in ident.app_roles


def test_entra_accepts_api_uri_audience(entra):
    v, make = entra
    assert v.validate(make(aud=f"api://{API_ID}")).oid == "o1"


@pytest.mark.parametrize("over,code", [
    ({"tid": "99999999-0000-0000-0000-000000000000"}, "TENANT_NOT_ALLOWED"),
    ({"iss": "https://login.microsoftonline.com/common/v2.0"}, "INVALID_TOKEN"),
    ({"aud": "graph"}, "INVALID_TOKEN"),
    ({"scp": "User.Read"}, "INSUFFICIENT_SCOPE"),
])
def test_entra_rejections(entra, over, code):
    v, make = entra
    with pytest.raises(AuthError) as ei:
        v.validate(make(**over))
    assert ei.value.code == code


def test_dev_mode_forbidden_in_production():
    with pytest.raises(ValueError):
        Settings(env="production", auth_mode="dev")
