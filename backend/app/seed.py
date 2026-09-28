"""Seed an eye care hospital: locations, roles, staff, catalogue, stock and sample pharmacy orders.

    python -m app.seed                      # seed if empty
    python -m app.seed --reset              # wipe and reseed (never in production)
    python -m app.seed --super-admin you@hospital.org   # pre-invite your Entra account as Super Admin
"""

import argparse
import asyncio
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.permissions import SUPER_ADMIN
from app.core.rbac import Principal, load_grants
from app.db.base import Base
from app.db.session import SessionLocal
from app.models import (
    Batch,
    DrugSchedule,
    Item,
    ItemType,
    LedgerReason,
    Location,
    LocationType,
    OrderChannel,
    Patient,
    Role,
    StockBalance,
    StockLedger,
    User,
    UserRole,
    UserStatus,
)
from app.schemas.pharmacy import OrderCreate, OrderLineIn, ReturnIn, ReturnLineIn
from app.services import pharmacy
from app.services.access import sync_catalogue

DOMAIN = "eyecare.example"

LOCATIONS = [
    ("CENTRAL-STORE", "Central Hospital Store", LocationType.warehouse),
    ("MAIN-PHARMACY", "Main Pharmacy", LocationType.pharmacy),
    ("OT-STORE", "OT Store", LocationType.ot_store),
]

# (display name, email local part, job title, department, [(role, location code | None)], status)
STAFF = [
    ("Asha Menon", "asha.menon", "Medical Superintendent", "Administration", [(SUPER_ADMIN, None)], "active"),
    ("Priya Sharma", "priya.sharma", "Operations Manager", "Administration", [("Hospital Admin", None)], "active"),
    ("Dr. Rajesh Kulkarni", "rajesh.kulkarni", "Senior Cataract Surgeon", "Cataract & IOL",
     [("Doctor / Surgeon", None)], "active"),
    ("Dr. Meera Iyer", "meera.iyer", "Vitreoretinal Surgeon", "Retina", [("Doctor / Surgeon", None)], "active"),
    ("Farhan Qureshi", "farhan.qureshi", "Chief Pharmacist", "Pharmacy",
     [("Pharmacist", "MAIN-PHARMACY")], "active"),
    ("Latha Nair", "latha.nair", "OT Nurse In-charge", "Operation Theatre", [("OT Nurse / Staff", None)], "active"),
    ("Vikram Joshi", "vikram.joshi", "Store Keeper", "Central Store",
     [("Store Keeper", "CENTRAL-STORE"), ("Store Keeper", "MAIN-PHARMACY")], "active"),
    ("Neha Kapoor", "neha.kapoor", "Procurement Officer", "Purchase", [("Procurement Officer", None)], "active"),
    ("Deepak Rao", "deepak.rao", "Accounts Executive", "Accounts", [("Billing / Accountant", None)], "active"),
    ("Ananya Sen", "ananya.sen", "Data Analyst", "Quality", [("Analyst", None)], "active"),
    ("Karan Malhotra", "karan.malhotra", "Pharmacy Assistant", "Pharmacy",
     [("Pharmacist", "MAIN-PHARMACY")], "invited"),
    ("Suresh Kumar", "suresh.kumar", "Former Pharmacist", "Pharmacy",
     [("Pharmacist", "MAIN-PHARMACY")], "inactive"),
]

# sku, name, generic, type, schedule, form, strength, gst, mrp, par_min, par_max, cold_chain
ITEMS = [
    ("DRP-MOXI-5", "Moxifloxacin 0.5% Eye Drops 5ml", "Moxifloxacin", ItemType.drug, DrugSchedule.H,
     "Eye drops", "0.5%", 12, 185, 60, 300, False),
    ("DRP-PRED-10", "Prednisolone Acetate 1% Eye Drops 10ml", "Prednisolone acetate", ItemType.drug,
     DrugSchedule.H, "Eye drops", "1%", 12, 95, 60, 300, False),
    ("DRP-TOBDEX-5", "Tobramycin 0.3% + Dexamethasone 0.1% Eye Drops 5ml", "Tobramycin + Dexamethasone",
     ItemType.drug, DrugSchedule.H, "Eye drops", "0.3%/0.1%", 12, 120, 40, 200, False),
    ("DRP-TIMO-5", "Timolol 0.5% Eye Drops 5ml", "Timolol maleate", ItemType.drug, DrugSchedule.H,
     "Eye drops", "0.5%", 12, 60, 30, 150, False),
    ("DRP-LATA-25", "Latanoprost 0.005% Eye Drops 2.5ml", "Latanoprost", ItemType.drug, DrugSchedule.H,
     "Eye drops", "0.005%", 12, 450, 20, 100, True),
    ("DRP-TROP-5", "Tropicamide 0.8% + Phenylephrine 5% Eye Drops 5ml", "Tropicamide + Phenylephrine",
     ItemType.drug, DrugSchedule.H, "Eye drops", "0.8%/5%", 12, 85, 40, 200, False),
    ("DRP-ATRO-5", "Atropine 1% Eye Drops 5ml", "Atropine sulphate", ItemType.drug, DrugSchedule.H,
     "Eye drops", "1%", 12, 45, 20, 100, False),
    ("DRP-NEPA-5", "Nepafenac 0.1% Eye Drops 5ml", "Nepafenac", ItemType.drug, DrugSchedule.H,
     "Eye drops", "0.1%", 12, 350, 30, 150, False),
    ("DRP-PROP-5", "Proparacaine 0.5% Eye Drops 5ml", "Proparacaine", ItemType.drug, DrugSchedule.H,
     "Eye drops", "0.5%", 12, 75, 20, 100, False),
    ("DRP-CMC-10", "Carboxymethylcellulose 0.5% Lubricant Eye Drops 10ml", "Carboxymethylcellulose",
     ItemType.drug, DrugSchedule.none, "Eye drops", "0.5%", 12, 150, 50, 300, False),
    ("SOL-PVI-5", "Povidone Iodine 5% Ophthalmic Solution 30ml", "Povidone iodine", ItemType.drug,
     DrugSchedule.none, "Solution", "5%", 12, 110, 20, 100, False),
    ("TAB-ACZ-250", "Acetazolamide 250mg Tablets (strip of 10)", "Acetazolamide", ItemType.drug,
     DrugSchedule.H, "Tablet", "250mg", 12, 60, 30, 150, False),
    ("CAP-TRAM-50", "Tramadol 50mg Capsules (strip of 10)", "Tramadol", ItemType.drug, DrugSchedule.H1,
     "Capsule", "50mg", 12, 90, 10, 50, False),
    ("INJ-RANI-10", "Ranibizumab 10mg/ml Injection 0.23ml", "Ranibizumab", ItemType.drug, DrugSchedule.H,
     "Injection", "10mg/ml", 5, 17500, 4, 20, True),
    ("CON-BSS-500", "Balanced Salt Solution 500ml", "BSS", ItemType.consumable, DrugSchedule.none,
     "Irrigation", "500ml", 12, 250, 40, 200, False),
    ("CON-OVD-2", "HPMC 2% Viscoelastic (OVD) 2ml", "Hydroxypropyl methylcellulose", ItemType.consumable,
     DrugSchedule.none, "Syringe", "2%", 12, 320, 30, 150, False),
    ("CON-KER-28", "Keratome Blade 2.8mm", None, ItemType.consumable, DrugSchedule.none, None, "2.8mm", 12,
     950, 20, 100, False),
    ("CON-CAN-27", "Hydrodissection Cannula 27G", None, ItemType.consumable, DrugSchedule.none, None, "27G", 12,
     45, 50, 300, False),
    ("CON-SUT-10", "Nylon Suture 10-0", None, ItemType.consumable, DrugSchedule.none, None, "10-0", 12, 480,
     10, 60, False),
    ("CON-DRAPE", "Sterile Ophthalmic Drape", None, ItemType.consumable, DrugSchedule.none, None, None, 12, 60,
     50, 300, False),
    ("CON-SHIELD", "Eye Shield (post-op)", None, ItemType.consumable, DrugSchedule.none, None, None, 12, 30,
     50, 300, False),
    ("IOL-HA-MONO", "Hydrophobic Acrylic Monofocal IOL (consignment)", None, ItemType.iol, DrugSchedule.none,
     None, None, 12, 12000, 0, 0, False),
]

# sku -> [(batch no, days to expiry, location code, qty, bin)]
BATCHES: dict[str, list[tuple[str, int, str, int, str]]] = {
    "DRP-MOXI-5": [("MX24A11", 20, "MAIN-PHARMACY", 40, "P-A1"), ("MX24B07", 240, "MAIN-PHARMACY", 150, "P-A1"),
                   ("MX25C02", 480, "CENTRAL-STORE", 400, "C-R1-S2")],
    "DRP-PRED-10": [("PA2405", -12, "MAIN-PHARMACY", 8, "P-A2"), ("PA2411", 150, "MAIN-PHARMACY", 120, "P-A2"),
                    ("PA2502", 420, "CENTRAL-STORE", 300, "C-R1-S3")],
    "DRP-TOBDEX-5": [("TD2409", 75, "MAIN-PHARMACY", 60, "P-A3"), ("TD2503", 390, "CENTRAL-STORE", 200, "C-R1-S4")],
    "DRP-TIMO-5": [("TM2412", 300, "MAIN-PHARMACY", 25, "P-B1")],
    "DRP-LATA-25": [("LT2408", 45, "MAIN-PHARMACY", 12, "FRIDGE-1"), ("LT2502", 330, "MAIN-PHARMACY", 30, "FRIDGE-1")],
    "DRP-TROP-5": [("TR2410", 200, "MAIN-PHARMACY", 90, "P-B2"), ("TR2410", 200, "OT-STORE", 40, "OT-1")],
    "DRP-ATRO-5": [("AT2406", 28, "MAIN-PHARMACY", 15, "P-B3"), ("AT2501", 500, "MAIN-PHARMACY", 60, "P-B3")],
    "DRP-NEPA-5": [("NP2411", 260, "MAIN-PHARMACY", 70, "P-B4")],
    "DRP-PROP-5": [("PP2410", 180, "OT-STORE", 30, "OT-2"), ("PP2410", 180, "MAIN-PHARMACY", 20, "P-C1")],
    "DRP-CMC-10": [("CM2409", 60, "MAIN-PHARMACY", 80, "P-C2"), ("CM2503", 540, "CENTRAL-STORE", 500, "C-R2-S1")],
    "SOL-PVI-5": [("PV2412", 365, "MAIN-PHARMACY", 40, "P-C3"), ("PV2412", 365, "OT-STORE", 30, "OT-3")],
    "TAB-ACZ-250": [("AZ2407", 210, "MAIN-PHARMACY", 50, "P-D1")],
    "CAP-TRAM-50": [("TRM2410", 400, "MAIN-PHARMACY", 20, "P-LOCK")],
    "INJ-RANI-10": [("RB24X3", 90, "MAIN-PHARMACY", 6, "FRIDGE-2")],
    "CON-BSS-500": [("BS2410", 330, "MAIN-PHARMACY", 60, "P-E1"), ("BS2410", 330, "OT-STORE", 80, "OT-4")],
    "CON-OVD-2": [("OV2409", 25, "OT-STORE", 12, "OT-5"), ("OV2502", 400, "MAIN-PHARMACY", 45, "P-E2")],
    "CON-KER-28": [("KB2406", 720, "MAIN-PHARMACY", 30, "P-E3"), ("KB2406", 720, "OT-STORE", 25, "OT-6")],
    "CON-CAN-27": [("CN2405", 600, "MAIN-PHARMACY", 120, "P-E4")],
    "CON-SUT-10": [("SU2408", 540, "MAIN-PHARMACY", 8, "P-E5")],
    "CON-DRAPE": [("DR2410", 700, "MAIN-PHARMACY", 150, "P-F1")],
    "CON-SHIELD": [("SH2410", 900, "MAIN-PHARMACY", 200, "P-F2")],
    "IOL-HA-MONO": [("IOL-SN-0001", 1100, "OT-STORE", 1, "IOL-CAB")],
}

PATIENTS = [
    ("MRN-100231", "Ramesh Patil", "9820011122", 67, "M"),
    ("MRN-100232", "Sunita Deshmukh", "9820011133", 58, "F"),
    ("MRN-100233", "Mohammed Shaikh", "9820011144", 72, "M"),
    ("MRN-100234", "Kavita Joshi", "9820011155", 45, "F"),
    ("MRN-100235", "Arjun Reddy", "9820011166", 33, "M"),
]


async def _principal(db: AsyncSession, email: str) -> Principal:
    u = await db.scalar(select(User).where(User.email == email))
    assert u
    return Principal(user_id=u.id, email=u.email, display_name=u.display_name, grants=await load_grants(db, u.id))


async def reset(db: AsyncSession) -> None:
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    await db.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    await db.execute(text("ALTER SEQUENCE pharmacy_order_no_seq RESTART"))
    await db.execute(text("ALTER SEQUENCE pharmacy_invoice_no_seq RESTART"))
    await db.commit()


async def seed(db: AsyncSession, super_admin_email: str | None = None) -> None:
    await sync_catalogue(db)
    if await db.scalar(select(func.count()).select_from(User)):
        if super_admin_email:
            await invite_super_admin(db, super_admin_email)
        print("Database already has users; skipping demo seed.")
        return

    locs = {}
    for code, name, typ in LOCATIONS:
        loc = Location(code=code, name=name, type=typ)
        db.add(loc)
        locs[code] = loc
    await db.flush()

    roles = {r.name: r for r in (await db.scalars(select(Role))).all()}
    now = datetime.now(UTC)
    for name, local, title, dept, assignments, status in STAFF:
        email = f"{local}@{DOMAIN}"
        u = User(email=email, display_name=name, job_title=title, department=dept, status=UserStatus(status),
                 # Pre-linked to the dev issuer's stable oid so dev sign-in works immediately.
                 oid=None if status == "invited" else f"dev-{email}",
                 tid=None if status == "invited" else "00000000-0000-0000-0000-000000000000",
                 last_login_at=None if status == "invited" else now - timedelta(hours=len(name)))
        u.role_assignments = [
            UserRole(role_id=roles[r].id, location_id=locs[lc].id if lc else None) for r, lc in assignments
        ]
        db.add(u)
    await db.flush()

    items = {}
    for sku, name, generic, typ, sched, form, strength, gst, mrp, pmin, pmax, cold in ITEMS:
        it = Item(sku=sku, name=name, generic_name=generic, type=typ, schedule=sched, dosage_form=form,
                  strength=strength, gst_rate=Decimal(gst), mrp=Decimal(mrp), par_min=pmin, par_max=pmax,
                  is_cold_chain=cold, hsn_code="3004" if typ == ItemType.drug else "9018", uom="unit")
        db.add(it)
        items[sku] = it
    await db.flush()

    today = date.today()
    batches: dict[tuple[str, str], Batch] = {}
    for sku, rows in BATCHES.items():
        it = items[sku]
        for n, (batch_no, days, loc_code, qty, bin_code) in enumerate(rows):
            key = (sku, batch_no)
            if key not in batches:
                b = Batch(item_id=it.id, batch_no=batch_no, expiry_date=today + timedelta(days=days),
                          mfg_date=today + timedelta(days=days - 730), mrp=it.mrp,
                          unit_cost=(it.mrp * Decimal("0.62")).quantize(Decimal("0.01")),
                          supplier_name="Sai Surgicals & Pharma Distributors",
                          received_at=now - timedelta(days=30 - n * 3))
                db.add(b)
                await db.flush()
                batches[key] = b
            b = batches[key]
            db.add(StockBalance(batch_id=b.id, location_id=locs[loc_code].id, bin_code=bin_code,
                                qty_on_hand=qty, qty_reserved=0))
            db.add(StockLedger(batch_id=b.id, location_id=locs[loc_code].id, qty_delta=qty,
                               reason=LedgerReason.receipt, note="Opening stock", ref_type="opening"))
    for mrn, name, phone, age, gender in PATIENTS:
        db.add(Patient(mrn=mrn, name=name, phone=phone, age=age, gender=gender))
    await db.commit()

    # Sample pharmacy activity through the real service layer (FEFO, audit, ledger).
    pharmacist = await _principal(db, f"farhan.qureshi@{DOMAIN}")
    surgeon = await _principal(db, f"rajesh.kulkarni@{DOMAIN}")
    nurse = await _principal(db, f"latha.nair@{DOMAIN}")
    pts = {p.mrn: p for p in (await db.scalars(select(Patient))).all()}

    def L(sku: str, qty: int) -> OrderLineIn:  # noqa: N802
        return OrderLineIn(item_id=items[sku].id, qty=qty)

    o1 = await pharmacy.create_order(db, pharmacist, OrderCreate(
        channel=OrderChannel.counter_sale, patient_id=pts["MRN-100231"].id, prescription_ref="OPD-RX-55120",
        prescriber_name="Dr. Rajesh Kulkarni", lines=[L("DRP-MOXI-5", 2), L("DRP-PRED-10", 1), L("CON-SHIELD", 1)]))
    await pharmacy.dispatch(db, pharmacist, o1.id)
    o2 = await pharmacy.create_order(db, pharmacist, OrderCreate(
        channel=OrderChannel.counter_sale, walk_in_name="Walk-in buyer", walk_in_phone="9876500001",
        lines=[L("DRP-CMC-10", 2)]))
    await pharmacy.dispatch(db, pharmacist, o2.id)
    o3 = await pharmacy.create_order(db, pharmacist, OrderCreate(
        channel=OrderChannel.counter_sale, patient_id=pts["MRN-100233"].id, prescription_ref="OPD-RX-55131",
        prescriber_name="Dr. Meera Iyer", lines=[L("DRP-TIMO-5", 1), L("TAB-ACZ-250", 2)]))
    await pharmacy.dispatch(db, pharmacist, o3.id)
    await pharmacy.return_items(db, pharmacist, o3.id, ReturnIn(
        lines=[ReturnLineIn(line_id=next(ln.id for ln in o3.lines if ln.item.sku == "TAB-ACZ-250"), qty=1)],
        reason="Patient already had one strip at home"))
    await pharmacy.create_order(db, surgeon, OrderCreate(
        channel=OrderChannel.requisition, department="OT-1 (Cataract)", surgery_ref="Phaco list 08:30",
        lines=[L("CON-BSS-500", 6), L("CON-OVD-2", 4), L("CON-KER-28", 4), L("DRP-TROP-5", 2)],
        notes="Morning phaco list - 4 cases"))
    o5 = await pharmacy.create_order(db, nurse, OrderCreate(
        channel=OrderChannel.requisition, department="Operation Theatre", lines=[L("CON-DRAPE", 20),
                                                                               L("SOL-PVI-5", 2)]))
    await pharmacy.dispatch(db, pharmacist, o5.id)
    await pharmacy.create_order(db, pharmacist, OrderCreate(
        channel=OrderChannel.counter_sale, patient_id=pts["MRN-100234"].id, prescription_ref="OPD-RX-55140",
        prescriber_name="Dr. Meera Iyer", lines=[L("DRP-LATA-25", 1)]))
    if super_admin_email:
        await invite_super_admin(db, super_admin_email)
    print(f"Seeded {len(STAFF)} staff, {len(ITEMS)} items, {len(batches)} batches, sample pharmacy orders.")


async def invite_super_admin(db: AsyncSession, email: str) -> None:
    email = email.lower()
    if await db.scalar(select(User.id).where(func.lower(User.email) == email)):
        print(f"{email} already exists")
        return
    sa = await db.scalar(select(Role).where(Role.name == SUPER_ADMIN))
    assert sa
    u = User(email=email, display_name=email.split("@")[0], status=UserStatus.invited)
    u.role_assignments = [UserRole(role_id=sa.id, location_id=None)]
    db.add(u)
    await db.commit()
    print(f"Invited {email} as {SUPER_ADMIN}; they will be linked on first Microsoft sign-in.")


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true")
    ap.add_argument("--super-admin")
    args = ap.parse_args()
    async with SessionLocal() as db:
        if args.reset:
            if get_settings().env in ("staging", "production"):
                raise SystemExit("Refusing to reset a staging/production database")
            await reset(db)
        await seed(db, args.super_admin)


if __name__ == "__main__":
    asyncio.run(main())
