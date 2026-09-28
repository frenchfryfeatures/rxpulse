import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, Numeric, Sequence, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Timestamps, UUIDPk
from app.models.identity import Location, User
from app.models.inventory import Batch, Item

ORDER_NO_SEQ = Sequence("pharmacy_order_no_seq", metadata=Base.metadata)
INVOICE_NO_SEQ = Sequence("pharmacy_invoice_no_seq", metadata=Base.metadata)


class Patient(UUIDPk, Timestamps, Base):
    __tablename__ = "patients"
    mrn: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str] = mapped_column(String(160), index=True)
    phone: Mapped[str | None] = mapped_column(String(20))
    age: Mapped[int | None] = mapped_column(Integer)
    gender: Mapped[str | None] = mapped_column(String(12))


class OrderChannel(enum.StrEnum):
    counter_sale = "counter_sale"   # patient / walk-in buyer at the pharmacy counter
    requisition = "requisition"     # doctor, surgeon, OT or ward request


class OrderStatus(enum.StrEnum):
    allocated = "allocated"
    dispatched = "dispatched"
    partially_returned = "partially_returned"
    returned = "returned"
    cancelled = "cancelled"


class PharmacyOrder(UUIDPk, Timestamps, Base):
    __tablename__ = "pharmacy_orders"
    order_no: Mapped[str] = mapped_column(String(40), unique=True)
    channel: Mapped[OrderChannel] = mapped_column(Enum(OrderChannel, name="order_channel"), index=True)
    status: Mapped[OrderStatus] = mapped_column(Enum(OrderStatus, name="order_status"), index=True)
    location_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("locations.id"))

    # counter_sale: registered patient or walk-in buyer
    patient_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("patients.id"))
    walk_in_name: Mapped[str | None] = mapped_column(String(160))
    walk_in_phone: Mapped[str | None] = mapped_column(String(20))
    prescription_ref: Mapped[str | None] = mapped_column(String(80))
    prescriber_name: Mapped[str | None] = mapped_column(String(160))

    # requisition: requested by a doctor / surgeon / OT staff member
    requested_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), index=True)
    department: Mapped[str | None] = mapped_column(String(120))
    surgery_ref: Mapped[str | None] = mapped_column(String(80))

    notes: Mapped[str | None] = mapped_column(Text)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))  # taxable value
    gst_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    total: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    invoice_no: Mapped[str | None] = mapped_column(String(40), unique=True)

    created_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    dispatched_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    location: Mapped[Location] = relationship()
    patient: Mapped[Patient | None] = relationship()
    requested_by: Mapped[User | None] = relationship(foreign_keys=[requested_by_id])
    created_by: Mapped[User] = relationship(foreign_keys=[created_by_id])
    lines: Mapped[list["PharmacyOrderLine"]] = relationship(
        back_populates="order", cascade="all, delete-orphan", order_by="PharmacyOrderLine.line_no"
    )


class PharmacyOrderLine(UUIDPk, Base):
    __tablename__ = "pharmacy_order_lines"
    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pharmacy_orders.id", ondelete="CASCADE"), index=True)
    line_no: Mapped[int] = mapped_column(Integer)
    item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("items.id"))
    qty: Mapped[int] = mapped_column(Integer)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))  # GST-inclusive
    gst_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    line_total: Mapped[Decimal] = mapped_column(Numeric(14, 2))

    order: Mapped[PharmacyOrder] = relationship(back_populates="lines")
    item: Mapped[Item] = relationship()
    allocations: Mapped[list["PharmacyOrderAllocation"]] = relationship(
        back_populates="line", cascade="all, delete-orphan"
    )


class PharmacyOrderAllocation(UUIDPk, Base):
    """FEFO allocation of an order line to a specific batch."""

    __tablename__ = "pharmacy_order_allocations"
    line_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("pharmacy_order_lines.id", ondelete="CASCADE"), index=True
    )
    batch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("batches.id"))
    qty: Mapped[int] = mapped_column(Integer)
    qty_returned: Mapped[int] = mapped_column(Integer, default=0)

    line: Mapped[PharmacyOrderLine] = relationship(back_populates="allocations")
    batch: Mapped[Batch] = relationship()
