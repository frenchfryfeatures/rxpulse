import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from app.models import DrugSchedule, ItemType, LedgerReason
from app.schemas.common import ORM

ExpiryStatus = Literal["expired", "critical", "warning", "ok"]


class ItemBase(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    generic_name: str | None = None
    type: ItemType
    schedule: DrugSchedule = DrugSchedule.none
    dosage_form: str | None = None
    strength: str | None = None
    manufacturer: str | None = None
    hsn_code: str | None = None
    gst_rate: Decimal = Field(default=Decimal("12"), ge=0, le=28)
    uom: str = "unit"
    mrp: Decimal = Field(ge=0)
    par_min: int = Field(default=0, ge=0)
    par_max: int = Field(default=0, ge=0)
    is_cold_chain: bool = False


class ItemCreate(ItemBase):
    sku: str = Field(min_length=2, max_length=40)


class ItemUpdate(BaseModel):
    name: str | None = None
    generic_name: str | None = None
    schedule: DrugSchedule | None = None
    dosage_form: str | None = None
    strength: str | None = None
    manufacturer: str | None = None
    hsn_code: str | None = None
    gst_rate: Decimal | None = Field(default=None, ge=0, le=28)
    mrp: Decimal | None = Field(default=None, ge=0)
    par_min: int | None = Field(default=None, ge=0)
    par_max: int | None = Field(default=None, ge=0)
    is_cold_chain: bool | None = None
    is_active: bool | None = None


class ItemOut(ItemBase, ORM):
    id: uuid.UUID
    sku: str
    is_active: bool
    on_hand: int = 0
    available: int = 0
    below_par: bool = False


class BatchRow(BaseModel):
    """One batch at one location (a stock_balances row), as shown in 'All Active Batches'."""

    balance_id: uuid.UUID
    batch_id: uuid.UUID
    item_id: uuid.UUID
    item_name: str
    sku: str
    item_type: ItemType
    schedule: DrugSchedule
    batch_no: str
    received_at: datetime
    expiry_date: date
    days_to_expiry: int
    expiry_status: ExpiryStatus
    location_id: uuid.UUID
    location_name: str
    bin_code: str | None
    qty_on_hand: int
    qty_reserved: int
    qty_available: int
    unit_cost: Decimal
    mrp: Decimal
    valuation: Decimal  # qty_on_hand × unit_cost


class ReceiptIn(BaseModel):
    item_id: uuid.UUID
    location_id: uuid.UUID
    batch_no: str = Field(min_length=1, max_length=60)
    expiry_date: date
    mfg_date: date | None = None
    qty: int = Field(gt=0)
    unit_cost: Decimal = Field(ge=0)
    mrp: Decimal | None = Field(default=None, ge=0)
    supplier_name: str | None = None
    bin_code: str | None = None


class AdjustmentIn(BaseModel):
    batch_id: uuid.UUID
    location_id: uuid.UUID
    qty_delta: int
    reason: Literal["count_correction", "damaged", "expired", "other"]
    note: str = Field(min_length=3, max_length=300)


class TransferIn(BaseModel):
    batch_id: uuid.UUID
    from_location_id: uuid.UUID
    to_location_id: uuid.UUID
    qty: int = Field(gt=0)
    note: str | None = None


class FefoPreviewIn(BaseModel):
    item_id: uuid.UUID
    location_id: uuid.UUID
    qty: int = Field(gt=0)


class FefoPick(BaseModel):
    batch_id: uuid.UUID
    batch_no: str
    expiry_date: date
    qty: int
    bin_code: str | None = None


class FefoPreviewOut(BaseModel):
    item_id: uuid.UUID
    requested: int
    allocatable: int
    shortfall: int
    picks: list[FefoPick]


class LedgerOut(ORM):
    id: uuid.UUID
    batch_id: uuid.UUID
    location_id: uuid.UUID
    qty_delta: int
    reason: LedgerReason
    note: str | None
    ref_type: str | None
    ref_id: str | None
    actor_id: uuid.UUID | None
    created_at: datetime
    item_name: str = ""
    sku: str = ""
    batch_no: str = ""
    location_name: str = ""
    actor_name: str | None = None


class ExpiryBucket(BaseModel):
    bucket: str
    batches: int
    units: int
    value: Decimal
