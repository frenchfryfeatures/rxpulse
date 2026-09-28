"""Access-token validation for Microsoft Entra ID (MSAL) and a local dev issuer.

Entra: tokens are acquired by the Next.js app with @azure/msal-react for the scope
`api://<API_CLIENT_ID>/access_as_user` and validated here against the tenant JWKS.

Dev: tokens are RS256-signed by a local key (see /api/v1/dev/token). The config refuses dev mode
in staging/production.
"""

import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.core.config import Settings

DEV_ISSUER = "https://rxpulse.local/dev"
DEV_AUDIENCE = "rxpulse-api-dev"
DEV_TENANT = "00000000-0000-0000-0000-000000000000"


class AuthError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class TokenIdentity:
    oid: str
    tid: str
    email: str | None
    name: str | None
    app_roles: frozenset[str]


# --------------------------------------------------------------------------- dev issuer
_dev_key_lock = threading.Lock()
_dev_private_key: rsa.RSAPrivateKey | None = None
DEV_KEY_PATH = Path(__file__).resolve().parents[2] / ".dev_jwt_key.pem"


def dev_private_key(persist: bool = True) -> rsa.RSAPrivateKey:
    global _dev_private_key
    with _dev_key_lock:
        if _dev_private_key is None:
            if persist and DEV_KEY_PATH.exists():
                _dev_private_key = serialization.load_pem_private_key(DEV_KEY_PATH.read_bytes(), None)  # type: ignore[assignment]
            else:
                _dev_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
                if persist:
                    DEV_KEY_PATH.write_bytes(
                        _dev_private_key.private_bytes(
                            serialization.Encoding.PEM,
                            serialization.PrivateFormat.PKCS8,
                            serialization.NoEncryption(),
                        )
                    )
                    DEV_KEY_PATH.chmod(0o600)
        return _dev_private_key  # type: ignore[return-value]


def mint_dev_token(
    *, oid: str, email: str, name: str, roles: list[str] | None = None, ttl: int = 3600, persist: bool = True,
    **overrides: Any,
) -> str:
    now = int(time.time())
    claims: dict[str, Any] = {
        "iss": DEV_ISSUER,
        "aud": DEV_AUDIENCE,
        "sub": oid,
        "oid": oid,
        "tid": DEV_TENANT,
        "preferred_username": email,
        "name": name,
        "scp": "access_as_user",
        "iat": now,
        "nbf": now,
        "exp": now + ttl,
    }
    if roles:
        claims["roles"] = roles
    claims.update(overrides)
    return jwt.encode(claims, dev_private_key(persist), algorithm="RS256", headers={"kid": "dev"})


# --------------------------------------------------------------------------- validation
class TokenValidator:
    def __init__(self, settings: Settings, *, persist_dev_key: bool = True):
        self.s = settings
        self._persist = persist_dev_key
        self._jwks: jwt.PyJWKClient | None = None
        if settings.auth_mode == "entra" and settings.azure_tenant_id:
            self._jwks = jwt.PyJWKClient(
                f"https://login.microsoftonline.com/{settings.azure_tenant_id}/discovery/v2.0/keys",
                cache_keys=True,
                lifespan=24 * 3600,
            )

    def validate(self, token: str) -> TokenIdentity:
        try:
            if self.s.auth_mode == "dev":
                claims = jwt.decode(
                    token,
                    dev_private_key(self._persist).public_key(),
                    algorithms=["RS256"],
                    audience=DEV_AUDIENCE,
                    issuer=DEV_ISSUER,
                    leeway=self.s.jwt_leeway_seconds,
                    options={"require": ["exp", "iat", "oid", "tid"]},
                )
            else:
                claims = self._validate_entra(token)
        except AuthError:
            raise
        except jwt.ExpiredSignatureError as e:
            raise AuthError("TOKEN_EXPIRED", "Access token has expired") from e
        except jwt.PyJWTError as e:
            raise AuthError("INVALID_TOKEN", f"Invalid access token: {e}") from e
        return self._identity(claims)

    def _validate_entra(self, token: str) -> dict[str, Any]:
        assert self._jwks is not None, "Entra JWKS client not configured"
        unverified = jwt.decode(token, options={"verify_signature": False})
        tid = unverified.get("tid")
        if tid not in self.s.allowed_tenants:
            raise AuthError("TENANT_NOT_ALLOWED", "Token tenant is not allowed")
        try:
            key = self._jwks.get_signing_key_from_jwt(token)
        except jwt.PyJWKClientError as e:  # unknown kid → PyJWKClient refetches once before failing
            raise AuthError("INVALID_TOKEN", f"Signing key not found: {e}") from e
        return jwt.decode(
            token,
            key.key,
            algorithms=["RS256"],
            audience=[self.s.azure_api_client_id, f"api://{self.s.azure_api_client_id}"],
            issuer=f"https://login.microsoftonline.com/{tid}/v2.0",
            leeway=self.s.jwt_leeway_seconds,
            options={"require": ["exp", "iat", "oid", "tid"]},
        )

    def _identity(self, claims: dict[str, Any]) -> TokenIdentity:
        # Only delegated (user) tokens are accepted. App-only worker tokens come with the agents phase.
        scopes = set(str(claims.get("scp", "")).split())
        if self.s.required_scope not in scopes:
            raise AuthError("INSUFFICIENT_SCOPE", f"Token is missing the '{self.s.required_scope}' scope")
        email = claims.get("preferred_username") or claims.get("email") or claims.get("upn")
        return TokenIdentity(
            oid=str(claims["oid"]),
            tid=str(claims["tid"]),
            email=email.lower() if email else None,
            name=claims.get("name"),
            app_roles=frozenset(claims.get("roles") or []),
        )
