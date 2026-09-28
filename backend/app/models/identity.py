import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, String, Text, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Timestamps, UUIDPk


class LocationType(enum.StrEnum):
    warehouse = "warehouse"
    pharmacy = "pharmacy"
    ot_store = "ot_store"


class Location(UUIDPk, Timestamps, Base):
    __tablename__ = "locations"
    code: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    type: Mapped[LocationType] = mapped_column(Enum(LocationType, name="location_type"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class UserStatus(enum.StrEnum):
    invited = "invited"
    active = "active"
    inactive = "inactive"


class User(UUIDPk, Timestamps, Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("tid", "oid", name="uq_users_tid_oid"),
        Index("uq_users_email_lower", text("lower(email)"), unique=True),
    )
    # Entra identity; NULL until the invited user signs in for the first time.
    oid: Mapped[str | None] = mapped_column(String(64))
    tid: Mapped[str | None] = mapped_column(String(64))
    email: Mapped[str] = mapped_column(String(254))
    display_name: Mapped[str] = mapped_column(String(160))
    job_title: Mapped[str | None] = mapped_column(String(120))
    department: Mapped[str | None] = mapped_column(String(120))
    status: Mapped[UserStatus] = mapped_column(Enum(UserStatus, name="user_status"), default=UserStatus.invited)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    invited_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))

    role_assignments: Mapped[list["UserRole"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", foreign_keys="UserRole.user_id"
    )


class Permission(Base):
    __tablename__ = "permissions"
    code: Mapped[str] = mapped_column(String(64), primary_key=True)
    module: Mapped[str] = mapped_column(String(40))
    description: Mapped[str] = mapped_column(String(200))


class Role(UUIDPk, Timestamps, Base):
    __tablename__ = "roles"
    name: Mapped[str] = mapped_column(String(80), unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)
    # Immutable roles (Super Admin) cannot be edited, renamed or deleted.
    is_immutable: Mapped[bool] = mapped_column(Boolean, default=False)

    permissions: Mapped[list["RolePermission"]] = relationship(
        back_populates="role", cascade="all, delete-orphan"
    )


class RolePermission(Base):
    __tablename__ = "role_permissions"
    role_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True)
    permission_code: Mapped[str] = mapped_column(
        ForeignKey("permissions.code", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[Role] = relationship(back_populates="permissions")


class UserRole(UUIDPk, Base):
    __tablename__ = "user_roles"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "role_id", "location_id", name="uq_user_roles_assignment", postgresql_nulls_not_distinct=True
        ),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("roles.id", ondelete="RESTRICT"), index=True)
    # NULL = the role applies at every location.
    location_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("locations.id", ondelete="CASCADE"))
    assigned_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped[User] = relationship(back_populates="role_assignments", foreign_keys=[user_id])
    role: Mapped[Role] = relationship()
    location: Mapped[Location | None] = relationship()
