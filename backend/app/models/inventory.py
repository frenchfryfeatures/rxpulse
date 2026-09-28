import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Timestamps, UUIDPk
from app.models.identity import Location


class ItemType(enum.StrEnum):
    drug = "drug"
    consumable = "consumable"
    iol = "iol"
    equipment = "equipment"


class DrugSchedule(enum.StrEnum):
    none = "none"   # OTC
    H = "H"
    H1 = "H1"
    X = "X"


class Item(UUIDPk, Timestamps, Base):
    __tablename__ = "items"
    sku: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    generic_name: Mapped[str | None] = mapped_column(String(200))
    type: Mapped[ItemType] = mapped_column(Enum(ItemType, name="item_type"))
    schedule: Mapped[DrugSchedule] = mapped_column(Enum(DrugSchedule, name="drug_schedule"), default=DrugSchedule.none)
    dosage_form: Mapped[str | None] = mapped_column(String(60))  # eye drops, tablet, injection...
    strength: Mapped[str | None] = mapped_column(String(60))
    manufacturer: Mapped[str | None] = mapped_column(String(120))
    hsn_code: Mapped[str | None] = mapped_column(String(12))
    gst_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("12"))
    uom: Mapped[str] = mapped_column(String(20), default="unit")
    mrp: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))  # GST-inclusive selling price
    par_min: Mapped[int] = mapped_column(Integer, default=0)
    par_max: Mapped[int] = mapped_column(Integer, default=0)
    is_cold_chain: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Batch(UUIDPk, Timestamps, Base):
    __tablename__ = "batches"
    __table_args__ = (UniqueConstraint("item_id", "batch_no", name="uq_batches_item_batch"),)
    item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("items.id"), index=True)
    batch_no: Mapped[str] = mapped_column(String(60))
    expiry_date: Mapped[date] = mapped_column(Date, index=True)
    mfg_date: Mapped[date | None] = mapped_column(Date)
    mrp: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    supplier_name: Mapped[str | None] = mapped_column(String(160))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    item: Mapped[Item] = relationship()


class StockBalance(UUIDPk, Base):
    """Current stock per batch per location. Only ever changed together with a StockLedger row."""

    __tablename__ = "stock_balances"
    __table_args__ = (
        UniqueConstraint("batch_id", "location_id", name="uq_stock_balances_batch_location"),
        CheckConstraint("qty_on_hand >= 0", name="on_hand_non_negative"),
        CheckConstraint("qty_reserved >= 0 AND qty_reserved <= qty_on_hand", name="reserved_within_on_hand"),
    )
    batch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("batches.id"), index=True)
    location_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("locations.id"), index=True)
    bin_code: Mapped[str | None] = mapped_column(String(40))
    qty_on_hand: Mapped[int] = mapped_column(Integer, default=0)
    qty_reserved: Mapped[int] = mapped_column(Integer, default=0)

    batch: Mapped[Batch] = relationship()
    location: Mapped[Location] = relationship()


class LedgerReason(enum.StrEnum):
    receipt = "receipt"
    adjustment = "adjustment"
    transfer_out = "transfer_out"
    transfer_in = "transfer_in"
    issue = "issue"          # pharmacy dispatch
    return_in = "return_in"  # pharmacy return
    writeoff = "writeoff"


class StockLedger(UUIDPk, Base):
    """Append-only record of every stock movement."""

    __tablename__ = "stock_ledger"
    __table_args__ = (Index("ix_stock_ledger_ref", "ref_type", "ref_id"),)
    batch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("batches.id"), index=True)
    location_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("locations.id"))
    qty_delta: Mapped[int] = mapped_column(Integer)
    reason: Mapped[LedgerReason] = mapped_column(Enum(LedgerReason, name="ledger_reason"))
    note: Mapped[str | None] = mapped_column(String(300))
    ref_type: Mapped[str | None] = mapped_column(String(40))
    ref_id: Mapped[str | None] = mapped_column(String(64))
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
