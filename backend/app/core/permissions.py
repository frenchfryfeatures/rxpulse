"""Permission catalogue and default (system) roles.

Permissions are "<resource>:<action>" strings. This module is the source of truth; `sync_catalogue`
upserts it into the database on startup/seed so role editors always see the full list.
"""

from dataclasses import dataclass

# module -> [(code, description)]
CATALOGUE: dict[str, list[tuple[str, str]]] = {
    "Dashboard": [("dashboard:view", "View the dashboard")],
    "Inventory": [
        ("inventory:view", "View stock, batches and expiry risk"),
        ("inventory:adjust", "Post stock adjustments"),
        ("inventory:transfer", "Transfer stock between locations"),
        ("inventory:writeoff", "Request write-offs of expired/damaged stock"),
        ("inventory:writeoff_approve", "Approve write-offs"),
        ("item:manage", "Create and edit the medicines & consumables catalogue"),
    ],
    "Procurement": [
        ("vendor:view", "View vendors"),
        ("vendor:manage", "Create and edit vendors"),
        ("po:view", "View purchase orders"),
        ("po:create", "Create purchase orders"),
        ("po:approve", "Approve purchase orders"),
        ("grn:create", "Receive goods into the store (GRN)"),
    ],
    "Pharmacy": [
        ("rx:view", "View prescriptions"),
        ("rx:create", "Write prescriptions"),
        ("pharmacy_order:view", "View all pharmacy orders"),
        ("pharmacy_order:create", "Create counter sales and requisitions at the pharmacy"),
        ("pharmacy_order:dispatch", "Dispatch pharmacy orders"),
        ("pharmacy_order:return", "Accept returns against pharmacy orders"),
        ("requisition:create", "Raise requisitions to the pharmacy (doctor / OT / ward)"),
        ("patient:manage", "Register patients"),
        ("controlled:register_view", "View the Schedule H1 register"),
    ],
    "Surgery": [
        ("surgery:view", "View surgery schedule and cases"),
        ("surgery:schedule", "Schedule surgeries"),
        ("bom:view", "View procedure bills of materials"),
        ("bom:manage", "Edit procedure bills of materials"),
        ("kit:issue", "Allocate and issue surgery kits"),
        ("intraop:log", "Log intra-operative usage"),
        ("kit:return", "Return unused kit items"),
    ],
    "Consignment IOL": [
        ("consignment:view", "View consignment IOL stock"),
        ("consignment:receive", "Receive consignment IOLs"),
        ("consignment:consume", "Record IOL implantation"),
        ("consignment:restock_request", "Raise vendor restock requests"),
    ],
    "Billing": [
        ("billing:view", "View billing and reconciliation"),
        ("billing:reconcile", "Reconcile surgery cases"),
        ("invoice:create", "Create invoices"),
        ("invoice:void", "Void invoices"),
        ("payable:manage", "Manage vendor payables"),
    ],
    "Analytics": [
        ("reports:view", "View reports"),
        ("reports:export", "Export reports"),
        ("forecast:view", "View demand forecasts"),
    ],
    "AI": [
        ("ai:chat", "Use the RxPulse assistant"),
        ("ai:approve_actions", "Approve actions proposed by agents"),
    ],
    "Administration": [
        ("staff:view", "View staff accounts"),
        ("staff:manage", "Invite, edit and deactivate staff"),
        ("role:manage", "Create and edit roles and permissions"),
        ("audit:view", "View the audit trail"),
        ("settings:manage", "Manage system settings"),
    ],
}

ALL_PERMISSIONS: frozenset[str] = frozenset(code for perms in CATALOGUE.values() for code, _ in perms)
MODULE_OF: dict[str, str] = {code: module for module, perms in CATALOGUE.items() for code, _ in perms}


def _expand(*patterns: str) -> frozenset[str]:
    out: set[str] = set()
    for p in patterns:
        if p == "*":
            out |= ALL_PERMISSIONS
        elif p.endswith(":*"):
            prefix = p[:-1]
            matched = {c for c in ALL_PERMISSIONS if c.startswith(prefix)}
            assert matched, f"pattern {p} matches nothing"
            out |= matched
        elif p.startswith("*:"):
            suffix = p[1:]
            out |= {c for c in ALL_PERMISSIONS if c.endswith(suffix)}
        else:
            assert p in ALL_PERMISSIONS, f"unknown permission {p}"
            out.add(p)
    return frozenset(out)


@dataclass(frozen=True)
class RoleDef:
    name: str
    description: str
    permissions: frozenset[str]
    immutable: bool = False


SUPER_ADMIN = "Super Admin"

DEFAULT_ROLES: list[RoleDef] = [
    RoleDef(SUPER_ADMIN, "Unrestricted access to the whole hospital system. Cannot be edited or deleted.",
            ALL_PERMISSIONS, immutable=True),
    RoleDef("Hospital Admin", "Operations oversight, approvals and staff management",
            ALL_PERMISSIONS - {"settings:manage", "role:manage"}),
    RoleDef("Doctor / Surgeon", "Prescribes, raises pharmacy requisitions and schedules surgeries",
            _expand("rx:*", "requisition:create", "surgery:view", "surgery:schedule", "bom:view",
                    "consignment:view", "forecast:view", "dashboard:view", "ai:chat")),
    RoleDef("Pharmacist", "Runs the hospital pharmacy: counter sales, requisitions, FEFO dispatch and returns",
            _expand("dashboard:view", "inventory:view", "inventory:adjust", "inventory:writeoff", "rx:view",
                    "pharmacy_order:*", "patient:manage", "controlled:register_view", "reports:view", "ai:chat")),
    RoleDef("OT Nurse / Staff", "Surgery kits, intra-op usage logging and pharmacy requisitions",
            _expand("dashboard:view", "surgery:view", "bom:view", "requisition:create", "kit:issue",
                    "intraop:log", "kit:return", "consignment:consume")),
    RoleDef("Store Keeper", "Hospital store: goods receipt, transfers and stock adjustments",
            _expand("dashboard:view", "inventory:view", "inventory:adjust", "inventory:transfer",
                    "inventory:writeoff", "item:manage", "grn:create", "consignment:receive", "po:view")),
    RoleDef("Procurement Officer", "Vendors, purchase orders and restock",
            _expand("dashboard:view", "inventory:view", "vendor:*", "po:view", "po:create",
                    "consignment:view", "consignment:restock_request", "forecast:view")),
    RoleDef("Billing / Accountant", "Reconciliation, invoices and vendor payables",
            _expand("dashboard:view", "billing:*", "invoice:*", "payable:manage", "reports:view",
                    "pharmacy_order:view")),
    RoleDef("Analyst", "Read-only access to stock, reports and forecasts",
            _expand("*:view", "reports:*") - {"staff:view", "audit:view"}),
]
