import os

os.environ.update(
    ENV="test",
    AUTH_MODE="dev",
    DATABASE_URL=os.environ.get("TEST_DATABASE_URL", "postgresql+asyncpg://rxpulse:rxpulse@localhost:5432/rxpulse_test"),
)

import pytest  # noqa: E402
from alembic.config import Config  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from alembic import command  # noqa: E402
from app.api.deps import get_validator  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.core.security import TokenValidator, dev_private_key, mint_dev_token  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Item, Location, Role  # noqa: E402
from app.seed import DOMAIN, reset, seed  # noqa: E402

dev_private_key(persist=False)  # in-memory signing key for the test run
app.dependency_overrides[get_validator] = lambda: TokenValidator(get_settings(), persist_dev_key=False)


def _alembic_upgrade() -> None:
    cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(os.path.dirname(__file__), "..", "alembic"))
    cfg.attributes["database_url"] = os.environ["DATABASE_URL"]
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")


@pytest.fixture(scope="session", autouse=True)
def migrated():
    _alembic_upgrade()


@pytest.fixture
async def db():
    async with SessionLocal() as s:
        yield s


@pytest.fixture(autouse=True)
async def fresh(migrated):
    """Every test starts from the seeded eye-hospital dataset."""
    async with SessionLocal() as s:
        await reset(s)
        await seed(s)
    yield
    await engine.dispose()


def email(local: str) -> str:
    return f"{local}@{DOMAIN}"


def token_for(local_or_email: str, **kw) -> str:
    e = local_or_email if "@" in local_or_email else email(local_or_email)
    return mint_dev_token(oid=kw.pop("oid", f"dev-{e}"), email=e, name=kw.pop("name", e), persist=False, **kw)


class Api:
    def __init__(self, client: AsyncClient):
        self.c = client

    def as_(self, who: str | None, **kw) -> AsyncClient:
        headers = {"Authorization": f"Bearer {token_for(who, **kw)}"} if who else {}
        return AsyncClient(transport=ASGITransport(app=app), base_url="http://test/api/v1", headers=headers)


@pytest.fixture
async def api():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test/api/v1") as c:
        yield Api(c)


# convenient role shortcuts
ADMIN, HOSP_ADMIN, SURGEON, RETINA, PHARMACIST = "asha.menon", "priya.sharma", "rajesh.kulkarni", "meera.iyer", \
    "farhan.qureshi"
NURSE, STORE, PROCURE, BILLING, ANALYST = "latha.nair", "vikram.joshi", "neha.kapoor", "deepak.rao", "ananya.sen"
INVITED, INACTIVE = "karan.malhotra", "suresh.kumar"


async def item_id(db, sku: str):
    return (await db.scalar(select(Item).where(Item.sku == sku))).id


async def location_id(db, code: str):
    return (await db.scalar(select(Location).where(Location.code == code))).id


async def role_id(db, name: str):
    return (await db.scalar(select(Role).where(Role.name == name))).id
