import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.models import LocationType, UserStatus
from app.schemas.common import ORM


class LocationOut(ORM):
    id: uuid.UUID
    code: str
    name: str
    type: LocationType


class PermissionOut(ORM):
    code: str
    module: str
    description: str


class RoleSummary(ORM):
    id: uuid.UUID
    name: str


class RoleOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str
    is_system: bool
    is_immutable: bool
    permissions: list[str]
    permission_count: int
    user_count: int


class RoleCreate(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    description: str = Field(default="", max_length=500)
    permissions: list[str] = []


class RoleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=80)
    description: str | None = Field(default=None, max_length=500)


class RolePermissionsUpdate(BaseModel):
    permissions: list[str]


class RoleAssignmentIn(BaseModel):
    role_id: uuid.UUID
    location_id: uuid.UUID | None = None  # None = all locations


class RoleAssignmentOut(BaseModel):
    role_id: uuid.UUID
    role_name: str
    location_id: uuid.UUID | None
    location_name: str | None


class StaffOut(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str
    job_title: str | None
    department: str | None
    status: UserStatus
    last_login_at: datetime | None
    linked: bool  # has signed in with Microsoft at least once
    roles: list[RoleAssignmentOut]


class StaffCreate(BaseModel):
    email: EmailStr
    display_name: str = Field(min_length=2, max_length=160)
    job_title: str | None = Field(default=None, max_length=120)
    department: str | None = Field(default=None, max_length=120)
    roles: list[RoleAssignmentIn] = Field(min_length=1)


class StaffUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=2, max_length=160)
    job_title: str | None = Field(default=None, max_length=120)
    department: str | None = Field(default=None, max_length=120)


class StaffRolesUpdate(BaseModel):
    roles: list[RoleAssignmentIn] = Field(min_length=1)


class MeOut(BaseModel):
    user: StaffOut
    permissions: list[str]
    # permission -> location ids (null entry = all locations)
    permission_scopes: dict[str, list[uuid.UUID | None]]
    locations: list[LocationOut]
