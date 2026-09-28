import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rbac import Principal
from app.models import AuditLog

_AUDIT_LOCK_KEY = 0x52785075  # "RxPu" – serialises the hash chain


def _canonical(v: Any) -> str:
    return json.dumps(v, sort_keys=True, default=str, separators=(",", ":"))


async def record(
    db: AsyncSession,
    actor: Principal | None,
    action: str,
    entity_type: str,
    entity_id: Any = None,
    *,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    actor_type: str = "user",
) -> None:
    """Append an audit row in the caller's transaction (committed together with the change)."""
    await db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _AUDIT_LOCK_KEY})
    prev = await db.scalar(select(AuditLog.hash).order_by(AuditLog.id.desc()).limit(1))
    ts = datetime.now(UTC)
    before_j = json.loads(_canonical(before)) if before is not None else None
    after_j = json.loads(_canonical(after)) if after is not None else None
    payload = {
        "ts": ts.isoformat(), "actor_id": str(actor.user_id) if actor else None, "actor_type": actor_type,
        "action": action, "entity_type": entity_type, "entity_id": str(entity_id) if entity_id else None,
        "before": before_j, "after": after_j,
    }
    digest = hashlib.sha256(((prev or "") + _canonical(payload)).encode()).hexdigest()
    db.add(AuditLog(
        ts=ts, actor_id=actor.user_id if actor else None, actor_email=actor.email if actor else None,
        actor_type=actor_type, action=action, entity_type=entity_type,
        entity_id=str(entity_id) if entity_id else None, before=before_j, after=after_j,
        request_id=actor.request_id if actor else None, ip=actor.ip if actor else None,
        prev_hash=prev, hash=digest,
    ))


async def verify_chain(db: AsyncSession) -> tuple[bool, int | None]:
    """Recompute the chain; returns (ok, first_bad_id)."""
    prev: str | None = None
    for row in (await db.scalars(select(AuditLog).order_by(AuditLog.id))).all():
        payload = {
            "ts": row.ts.astimezone(UTC).isoformat(), "actor_id": str(row.actor_id) if row.actor_id else None,
            "actor_type": row.actor_type, "action": row.action, "entity_type": row.entity_type,
            "entity_id": row.entity_id, "before": row.before, "after": row.after,
        }
        digest = hashlib.sha256(((prev or "") + _canonical(payload)).encode()).hexdigest()
        if row.prev_hash != prev or row.hash != digest:
            return False, row.id
        prev = row.hash
    return True, None
