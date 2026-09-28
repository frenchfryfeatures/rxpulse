import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator

from app.models import OrderChannel, OrderStatus
from app.schemas.common import ORM


class PatientIn(BaseModel):
    mrn: str = Field(min_length=2, max_length=40)
    name: str = Field(min_length=2, max_length=160)
    phone: str | None = Field(default=None, max_length=20)
    age: int | None = Field(default=None, ge=0, le=130)
    gender: str | None = None


class PatientOut(PatientIn, ORM):
    id: uuid.UUID


class OrderLineIn(BaseModel):
    item_id: uuid.UUID
    qty: int = Field(gt=0, le=10000)


class OrderCreate(BaseModel):
    channel: OrderChannel
    lines: list[OrderLineIn] = Field(min_length=1, max_length=100)
    # counter_sale
    patient_id: uuid.UUID | None = None
    walk_in_name: str | None = Field(default=None, max_length=160)
    walk_in_phone: str | None = Field(default=None, max_length=20)
    prescription_ref: str | None = Field(default=None, max_length=80)
    prescriber_name: str | None = Field(default=None, max_length=160)
    # requisition
    requested_by_id: uuid.UUID | None = None  # defaults to the caller
    department: str | None = Field(default=None, max_length=120)
    surgery_ref: str | None = Field(default=None, max_length=80)
    notes: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def _channel_fields(self) -> "OrderCreate":
        if self.channel == OrderChannel.counter_sale and not (self.patient_id or self.walk_in_name):
            raise ValueError("A counter sale needs a registered patient or a walk-in buyer name")
        if self.channel == OrderChannel.requisition and not self.department:
            raise ValueError("A requisition needs a department (e.g. OT-1, Retina clinic)")
        item_ids = [line.item_id for line in self.lines]
        if len(item_ids) != len(set(item_ids)):
            raise ValueError("Each item may appear only once per order")
        return self


class AllocationOut(BaseModel):
    batch_id: uuid.UUID
    batch_no: str
    expiry_date: date
    qty: int
    qty_returned: int


class OrderLineOut(BaseModel):
    id: uuid.UUID
    line_no: int
    item_id: uuid.UUID
    item_name: str
    sku: str
    schedule: str
    qty: int
    unit_price: Decimal
    gst_rate: Decimal
    line_total: Decimal
    qty_returned: int
    allocations: list[AllocationOut]


class OrderOut(BaseModel):
    id: uuid.UUID
    order_no: str
    channel: OrderChannel
    status: OrderStatus
    location_id: uuid.UUID
    location_name: str
    party_name: str  # patient / walk-in buyer / requesting doctor
    patient: PatientOut | None
    walk_in_name: str | None
    walk_in_phone: str | None
    prescription_ref: str | None
    prescriber_name: str | None
    requested_by_id: uuid.UUID | None
    requested_by_name: str | None
    department: str | None
    surgery_ref: str | None
    notes: str | None
    subtotal: Decimal
    gst_amount: Decimal
    total: Decimal
    invoice_no: str | None
    created_at: datetime
    created_by_name: str
    dispatched_at: datetime | None
    lines: list[OrderLineOut]


class ReturnLineIn(BaseModel):
    line_id: uuid.UUID
    qty: int = Field(gt=0)


class ReturnIn(BaseModel):
    lines: list[ReturnLineIn] = Field(min_length=1)
    reason: str = Field(min_length=3, max_length=300)


class PickListRow(BaseModel):
    line_no: int
    item_name: str
    sku: str
    batch_no: str
    expiry_date: date
    bin_code: str | None
    qty: int


class PickListOut(BaseModel):
    order_no: str
    location_name: str
    party_name: str
    rows: list[PickListRow]
