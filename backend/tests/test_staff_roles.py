from sqlalchemy import select

from app.models import User
from tests.conftest import ADMIN, HOSP_ADMIN, PHARMACIST, email, location_id, role_id


async def _user_id(db, local):
    return (await db.scalar(select(User).where(User.email == email(local)))).id


async def test_roles_list_has_real_counts(api):
    async with api.as_(ADMIN) as c:
        roles = {r["name"]: r for r in (await c.get("/roles")).json()}
    assert roles["Super Admin"]["permission_count"] == len(roles["Super Admin"]["permissions"]) > 40
    assert roles["Super Admin"]["user_count"] == 1
    assert roles["Pharmacist"]["user_count"] == 2  # active + invited (inactive excluded)
    assert roles["Super Admin"]["is_immutable"] and roles["Pharmacist"]["is_system"]


async def test_staff_list_includes_roles_and_paginates(api):
    async with api.as_(ADMIN) as c:
        page = (await c.get("/staff", params={"page_size": 5})).json()
        assert page["total"] == 12 and len(page["items"]) == 5
        found = (await c.get("/staff", params={"q": "farhan"})).json()["items"]
    assert found[0]["roles"][0]["role_name"] == "Pharmacist"
    assert found[0]["roles"][0]["location_name"] == "Main Pharmacy"


async def test_invite_staff_and_duplicate(api, db):
    body = {"email": "New.Nurse@EyeCare.example", "display_name": "Rina Das", "job_title": "Staff Nurse",
            "roles": [{"role_id": str(await role_id(db, "OT Nurse / Staff"))}]}
    async with api.as_(HOSP_ADMIN) as c:
        r = await c.post("/staff", json=body)
        assert r.status_code == 201, r.text
        assert r.json()["status"] == "invited" and r.json()["email"] == "new.nurse@eyecare.example"
        r = await c.post("/staff", json=body)
    assert r.status_code == 409 and r.json()["code"] == "EMAIL_EXISTS"
    # The invited nurse can sign in and gets linked
    async with api.as_("new.nurse@eyecare.example", oid="entra-rina") as c:
        me = (await c.get("/me")).json()
    assert me["user"]["status"] == "active" and "intraop:log" in me["permissions"]


async def test_invite_requires_a_role(api):
    async with api.as_(ADMIN) as c:
        r = await c.post("/staff", json={"email": "x@eyecare.example", "display_name": "X Y", "roles": []})
    assert r.status_code == 422


async def test_no_privilege_escalation_via_assignment(api, db):
    # Hospital Admin lacks role:manage/settings:manage, so cannot hand out Super Admin.
    body = {"email": "sneaky@eyecare.example", "display_name": "Sneaky",
            "roles": [{"role_id": str(await role_id(db, "Super Admin"))}]}
    async with api.as_(HOSP_ADMIN) as c:
        r = await c.post("/staff", json=body)
    assert r.status_code == 403 and set(r.json()["missing"]) == {"role:manage", "settings:manage"}


async def test_cannot_change_own_roles_or_deactivate_self(api, db):
    me = await _user_id(db, ADMIN)
    async with api.as_(ADMIN) as c:
        r = await c.put(f"/staff/{me}/roles", json={"roles": [{"role_id": str(await role_id(db, "Analyst"))}]})
        assert r.status_code == 403
        r = await c.post(f"/staff/{me}/deactivate")
        assert r.status_code == 403


async def test_last_super_admin_protected(api, db):
    # Promote Priya to Super Admin, then Priya demotes Asha: allowed (one SA remains).
    priya, asha = await _user_id(db, HOSP_ADMIN), await _user_id(db, ADMIN)
    sa = str(await role_id(db, "Super Admin"))
    async with api.as_(ADMIN) as c:
        assert (await c.put(f"/staff/{priya}/roles", json={"roles": [{"role_id": sa}]})).status_code == 200
    async with api.as_(HOSP_ADMIN) as c:
        r = await c.put(f"/staff/{asha}/roles", json={"roles": [{"role_id": str(await role_id(db, "Analyst"))}]})
        assert r.status_code == 200, r.text
    # Asha is now an Analyst and can't manage staff. Priya is the only SA and can't lose it:
    async with api.as_(ADMIN) as c:
        assert (await c.get("/staff")).status_code == 403


async def test_last_super_admin_cannot_be_deactivated(api, db):
    # Priya gets a custom role holding every permission, but she is not a Super Admin.
    from app.core.permissions import ALL_PERMISSIONS

    priya, asha = await _user_id(db, HOSP_ADMIN), await _user_id(db, ADMIN)
    async with api.as_(ADMIN) as c:
        rid = (await c.post("/roles", json={"name": "Everything", "permissions": sorted(ALL_PERMISSIONS)})).json()["id"]
        assert (await c.put(f"/staff/{priya}/roles", json={"roles": [{"role_id": rid}]})).status_code == 200
    async with api.as_(HOSP_ADMIN) as c:
        r = await c.post(f"/staff/{asha}/deactivate")
    assert r.status_code == 409 and r.json()["code"] == "LAST_SUPER_ADMIN"


async def test_deactivation_takes_effect_immediately(api, db):
    pharm = await _user_id(db, PHARMACIST)
    async with api.as_(PHARMACIST) as c:
        assert (await c.get("/me")).status_code == 200
    async with api.as_(HOSP_ADMIN) as c:
        r = await c.post(f"/staff/{pharm}/deactivate")
        assert r.status_code == 200 and r.json()["status"] == "inactive"
    async with api.as_(PHARMACIST) as c:
        r = await c.get("/me")
    assert r.status_code == 403 and r.json()["code"] == "ACCOUNT_DEACTIVATED"
    async with api.as_(HOSP_ADMIN) as c:
        assert (await c.post(f"/staff/{pharm}/reactivate")).json()["status"] == "active"


async def test_location_scoped_assignment(api, db):
    analyst = await _user_id(db, "ananya.sen")
    body = {"roles": [{"role_id": str(await role_id(db, "Store Keeper")),
                       "location_id": str(await location_id(db, "OT-STORE"))}]}
    async with api.as_(ADMIN) as c:
        r = await c.put(f"/staff/{analyst}/roles", json=body)
    assert r.status_code == 200 and r.json()["roles"][0]["location_name"] == "OT Store"
    async with api.as_("ananya.sen") as c:
        rows = (await c.get("/batches", params={"page_size": 100})).json()["items"]
    assert {r["location_name"] for r in rows} == {"OT Store"}


async def test_custom_role_lifecycle(api, db):
    async with api.as_(ADMIN) as c:
        r = await c.post("/roles", json={"name": "Night Pharmacist", "description": "Night shift",
                                         "permissions": ["pharmacy_order:view", "pharmacy_order:dispatch"]})
        assert r.status_code == 201 and r.json()["permission_count"] == 2
        rid = r.json()["id"]
        r = await c.put(f"/roles/{rid}/permissions", json={"permissions": ["pharmacy_order:view"]})
        assert r.json()["permissions"] == ["pharmacy_order:view"]
        r = await c.put(f"/roles/{rid}/permissions", json={"permissions": ["not:a_permission"]})
        assert r.status_code == 422
        r = await c.patch(f"/roles/{rid}", json={"name": "Night Shift Pharmacist"})
        assert r.json()["name"] == "Night Shift Pharmacist"
        assert (await c.delete(f"/roles/{rid}")).status_code == 204


async def test_system_role_rules(api, db):
    async with api.as_(ADMIN) as c:
        sa = await role_id(db, "Super Admin")
        assert (await c.put(f"/roles/{sa}/permissions", json={"permissions": []})).status_code == 403
        ph = await role_id(db, "Pharmacist")
        assert (await c.delete(f"/roles/{ph}")).status_code == 403
        assert (await c.patch(f"/roles/{ph}", json={"name": "Chemist"})).status_code == 403
        # System (non-immutable) role permissions can be tuned
        r = await c.put(f"/roles/{ph}/permissions", json={"permissions": ["pharmacy_order:view", "inventory:view"]})
        assert r.status_code == 200 and r.json()["permission_count"] == 2


async def test_role_in_use_cannot_be_deleted(api, db):
    analyst = await _user_id(db, "ananya.sen")
    async with api.as_(ADMIN) as c:
        rid = (await c.post("/roles", json={"name": "Temp", "permissions": ["reports:view"]})).json()["id"]
        await c.put(f"/staff/{analyst}/roles", json={"roles": [{"role_id": rid}]})
        r = await c.delete(f"/roles/{rid}")
    assert r.status_code == 409 and r.json()["code"] == "ROLE_IN_USE"


async def test_staff_changes_are_audited(api, db):
    pharm = await _user_id(db, PHARMACIST)
    async with api.as_(ADMIN) as c:
        await c.patch(f"/staff/{pharm}", json={"job_title": "Head Pharmacist"})
        rows = (await c.get("/audit", params={"entity_id": str(pharm)})).json()["items"]
        assert rows[0]["action"] == "staff.update"
        assert rows[0]["before"]["job_title"] == "Chief Pharmacist"
        assert rows[0]["after"]["job_title"] == "Head Pharmacist"
        assert rows[0]["actor_email"] == email(ADMIN)
        assert (await c.get("/audit/verify")).json() == {"ok": True, "first_bad_id": None}
