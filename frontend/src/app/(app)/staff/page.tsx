"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Lock, Pencil, Plus, RotateCcw, Shield, UserX } from "lucide-react";
import { useState } from "react";
import { Can, Guard } from "@/components/auth/Guard";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardHeader, PageHeader } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/dialog";
import { EmptyRow, FilterSelect, LoadingRows, Pagination, SearchInput, Table, Td, Th, Toolbar } from "@/components/ui/table";
import { useToast } from "@/components/ui/toast";
import { errorMessage, useApi } from "@/lib/api/client";
import type { Page, Role, Staff } from "@/lib/api/types";
import { useMe } from "@/lib/auth/MeProvider";
import { relative } from "@/lib/format";
import { RoleDialog } from "./RoleDialog";
import { StaffDialog } from "./StaffDialog";

type StatusFilter = "all" | "active" | "invited" | "inactive";

export default function StaffPage() {
  return (
    <Guard anyOf={["staff:view"]}>
      <StaffAndRoles />
    </Guard>
  );
}

function StaffAndRoles() {
  const api = useApi();
  const qc = useQueryClient();
  const toast = useToast();
  const { me, can } = useMe();
  const [q, setQ] = useState("");
  const [status, setStatus] = useState<StatusFilter>("all");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [editing, setEditing] = useState<Staff | "new" | null>(null);
  const [roleEditing, setRoleEditing] = useState<Role | "new" | null>(null);
  const [toggle, setToggle] = useState<Staff | null>(null);

  const staff = useQuery({
    queryKey: ["staff", q, status, page, pageSize],
    queryFn: () => api<Page<Staff>>("/staff", { query: { q, status: status === "all" ? undefined : status, page, page_size: pageSize } }),
    placeholderData: keepPreviousData,
  });
  const roles = useQuery({ queryKey: ["roles"], queryFn: () => api<Role[]>("/roles") });

  const toggleMut = useMutation({
    mutationFn: (s: Staff) => api<Staff>(`/staff/${s.id}/${s.status === "inactive" ? "reactivate" : "deactivate"}`, { method: "POST" }),
    onSuccess: (s) => {
      toast("success", `${s.display_name} ${s.status === "inactive" ? "deactivated" : "reactivated"}`);
      setToggle(null);
      qc.invalidateQueries({ queryKey: ["staff"] });
      qc.invalidateQueries({ queryKey: ["roles"] });
    },
  });

  const activeCount = (roles.data ?? []).length ? staff.data?.items.filter((s) => s.status === "active").length : undefined;
  const manage = can("staff:manage");

  return (
    <>
      <PageHeader
        title="Staff & Role-Based Access Control (RBAC)"
        subtitle="Manage hospital staff, their roles and location scope, and granular permissions. Identities come from Microsoft Entra ID."
        actions={<Can permission="staff:manage"><Button variant="primary" icon={<Plus className="h-4 w-4" />} onClick={() => setEditing("new")}>Add Staff Member</Button></Can>}
      />

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_380px]">
        <Card className="overflow-hidden">
          <CardHeader title="Registered Staff Accounts"
            actions={activeCount !== undefined && <span className="text-xs text-slate-400">{staff.data?.total ?? 0} accounts</span>} />
          <Toolbar onRefresh={() => staff.refetch()} refreshing={staff.isFetching} shown={staff.data?.items.length} total={staff.data?.total}>
            <SearchInput value={q} onChange={(v) => { setQ(v); setPage(1); }} placeholder="Search name or email…" />
            <FilterSelect<StatusFilter> value={status} onChange={(v) => { setStatus(v); setPage(1); }} options={[
              { value: "all", label: "All statuses" }, { value: "active", label: "Active" },
              { value: "invited", label: "Invited" }, { value: "inactive", label: "Inactive" }]} />
          </Toolbar>
          <Table>
            <thead><tr>
              <Th>Staff name</Th><Th>Email address</Th><Th>Assigned role(s)</Th><Th>Account status</Th><Th>Last sign-in</Th>
              <Th className="text-right">Actions</Th>
            </tr></thead>
            <tbody>
              {staff.isPending && <LoadingRows colSpan={6} />}
              {staff.data?.items.length === 0 && <EmptyRow colSpan={6}>No staff match your filters.</EmptyRow>}
              {staff.data?.items.map((s) => (
                <tr key={s.id} className="hover:bg-slate-50/60">
                  <Td>
                    <p className="font-medium text-slate-900">{s.display_name}</p>
                    <p className="text-xs text-slate-400">{[s.job_title, s.department].filter(Boolean).join(" · ")}</p>
                  </Td>
                  <Td className="font-mono text-xs text-slate-600">{s.email}</Td>
                  <Td>
                    <div className="flex flex-wrap gap-1">
                      {s.roles.map((r) => (
                        <Badge key={r.role_id + (r.location_id ?? "")} tone="blue" uppercase={false}>
                          {r.role_name}{r.location_name && <span className="ml-1 font-normal text-blue-500">@ {r.location_name}</span>}
                        </Badge>
                      ))}
                      {s.roles.length === 0 && <span className="text-xs text-rose-500">No role</span>}
                    </div>
                  </Td>
                  <Td>
                    {s.status === "active" && <Badge tone="green">Active</Badge>}
                    {s.status === "invited" && <Badge tone="amber">Invited</Badge>}
                    {s.status === "inactive" && <Badge tone="red">Inactive</Badge>}
                  </Td>
                  <Td className="text-xs text-slate-500">{s.status === "invited" ? "Pending first sign-in" : relative(s.last_login_at)}</Td>
                  <Td className="text-right">
                    {manage && (
                      <div className="flex justify-end gap-2">
                        <Button size="sm" icon={<Pencil className="h-3.5 w-3.5" />} onClick={() => setEditing(s)}>Edit</Button>
                        {s.id !== me.user.id && (s.status === "inactive"
                          ? <Button size="sm" variant="outline-brand" icon={<RotateCcw className="h-3.5 w-3.5" />} onClick={() => setToggle(s)}>Reactivate</Button>
                          : <Button size="sm" variant="outline-danger" icon={<UserX className="h-3.5 w-3.5" />} onClick={() => setToggle(s)}>Deactivate</Button>)}
                      </div>
                    )}
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
          <Pagination page={page} pageSize={pageSize} total={staff.data?.total ?? 0} onPage={setPage}
            onPageSize={(n) => { setPageSize(n); setPage(1); }} noun="staff accounts" />
        </Card>

        <Card className="h-fit">
          <CardHeader title="System & Custom Roles" icon={<Shield className="h-4 w-4" />}
            actions={<Can permission="role:manage"><Button size="sm" icon={<Plus className="h-3.5 w-3.5" />} onClick={() => setRoleEditing("new")}>New role</Button></Can>} />
          <ul className="divide-y divide-slate-100">
            {roles.data?.map((r) => (
              <li key={r.id}>
                <button onClick={() => setRoleEditing(r)} className="w-full px-5 py-3.5 text-left hover:bg-slate-50">
                  <div className="flex items-center justify-between gap-3">
                    <span className="flex items-center gap-1.5 text-sm font-semibold text-slate-900">
                      {r.name}{r.is_immutable && <Lock className="h-3 w-3 text-slate-400" />}
                    </span>
                    <span className="text-[11px] text-slate-400">{r.permission_count} permissions</span>
                  </div>
                  <p className="mt-0.5 text-xs text-slate-500">{r.description}</p>
                  <div className="mt-1.5 flex gap-2 text-[11px]">
                    <span className="text-slate-400">{r.user_count} user{r.user_count === 1 ? "" : "s"}</span>
                    <span className={r.is_system ? "text-slate-400" : "text-violet-600"}>{r.is_system ? "System role" : "Custom role"}</span>
                  </div>
                </button>
              </li>
            ))}
          </ul>
        </Card>
      </div>

      {editing && <StaffDialog staff={editing === "new" ? null : editing} roles={roles.data ?? []} onClose={() => setEditing(null)} />}
      {roleEditing && <RoleDialog role={roleEditing === "new" ? null : roleEditing} onClose={() => setRoleEditing(null)} />}
      <ConfirmDialog
        open={!!toggle}
        onClose={() => { setToggle(null); toggleMut.reset(); }}
        onConfirm={() => toggle && toggleMut.mutate(toggle)}
        loading={toggleMut.isPending}
        error={toggleMut.error ? errorMessage(toggleMut.error) : null}
        tone={toggle?.status === "inactive" ? "primary" : "danger"}
        title={toggle?.status === "inactive" ? "Reactivate staff member?" : "Deactivate staff member?"}
        confirmLabel={toggle?.status === "inactive" ? "Reactivate" : "Deactivate"}
      >
        {toggle?.status === "inactive"
          ? <p><b>{toggle?.display_name}</b> will regain access with their existing roles.</p>
          : <p><b>{toggle?.display_name}</b> will lose access to RxPulse immediately, even if they are still signed in to Microsoft. Their history is kept.</p>}
      </ConfirmDialog>
    </>
  );
}
