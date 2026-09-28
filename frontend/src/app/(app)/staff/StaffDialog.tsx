"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { ErrorBanner, Field, Input, Select } from "@/components/ui/form";
import { useToast } from "@/components/ui/toast";
import { errorMessage, useApi } from "@/lib/api/client";
import type { Role, RoleAssignmentIn, Staff } from "@/lib/api/types";
import { useMe } from "@/lib/auth/MeProvider";

type Row = { role_id: string; location_id: string };

export function StaffDialog({ staff, roles, onClose }: { staff: Staff | null; roles: Role[]; onClose: () => void }) {
  const api = useApi();
  const qc = useQueryClient();
  const toast = useToast();
  const { me } = useMe();
  const isSelf = staff?.id === me.user.id;
  const [form, setForm] = useState({
    email: staff?.email ?? "",
    display_name: staff?.display_name ?? "",
    job_title: staff?.job_title ?? "",
    department: staff?.department ?? "",
  });
  const [rows, setRows] = useState<Row[]>(
    staff?.roles.map((r) => ({ role_id: r.role_id, location_id: r.location_id ?? "" })) ?? [{ role_id: "", location_id: "" }],
  );

  const assignments = (): RoleAssignmentIn[] =>
    rows.filter((r) => r.role_id).map((r) => ({ role_id: r.role_id, location_id: r.location_id || null }));

  const save = useMutation({
    mutationFn: async () => {
      const details = { display_name: form.display_name, job_title: form.job_title || null, department: form.department || null };
      if (!staff) return api<Staff>("/staff", { method: "POST", body: { email: form.email, ...details, roles: assignments() } });
      await api<Staff>(`/staff/${staff.id}`, { method: "PATCH", body: details });
      const before = JSON.stringify(staff.roles.map((r) => [r.role_id, r.location_id ?? ""]).sort());
      const after = JSON.stringify(rows.filter((r) => r.role_id).map((r) => [r.role_id, r.location_id]).sort());
      if (!isSelf && before !== after) {
        return api<Staff>(`/staff/${staff.id}/roles`, { method: "PUT", body: { roles: assignments() } });
      }
      return staff;
    },
    onSuccess: () => {
      toast("success", staff ? "Staff member updated" : `Invitation created for ${form.email}`);
      qc.invalidateQueries({ queryKey: ["staff"] });
      qc.invalidateQueries({ queryKey: ["roles"] });
      onClose();
    },
  });

  const valid = form.display_name.trim().length >= 2 && (staff || /\S+@\S+\.\S+/.test(form.email)) && assignments().length > 0;

  return (
    <Dialog open onClose={onClose} size="lg"
      title={staff ? `Edit ${staff.display_name}` : "Add staff member"}
      description={staff ? "Name and email come from Microsoft Entra ID; roles and location scope are managed here."
        : "They'll be linked to their Microsoft account automatically the first time they sign in with this email."}
      footer={<><Button onClick={onClose}>Cancel</Button>
        <Button variant="primary" disabled={!valid} loading={save.isPending} onClick={() => save.mutate()}>{staff ? "Save changes" : "Add staff member"}</Button></>}>
      <div className="space-y-5">
        <ErrorBanner message={save.error ? errorMessage(save.error) : null} />
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Work email (Microsoft account)" required>
            <Input type="email" value={form.email} disabled={!!staff} placeholder="name@hospital.org"
              onChange={(e) => setForm({ ...form, email: e.target.value })} />
          </Field>
          <Field label="Display name" required>
            <Input value={form.display_name} onChange={(e) => setForm({ ...form, display_name: e.target.value })} />
          </Field>
          <Field label="Job title"><Input value={form.job_title} onChange={(e) => setForm({ ...form, job_title: e.target.value })} /></Field>
          <Field label="Department"><Input value={form.department} onChange={(e) => setForm({ ...form, department: e.target.value })} /></Field>
        </div>

        <div>
          <div className="mb-2 flex items-center justify-between">
            <p className="text-xs font-medium text-slate-700">Roles & location scope <span className="text-rose-500">*</span></p>
            {!isSelf && <Button size="sm" variant="ghost" icon={<Plus className="h-3.5 w-3.5" />}
              onClick={() => setRows([...rows, { role_id: "", location_id: "" }])}>Add role</Button>}
          </div>
          {isSelf && <p className="mb-2 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-700">You can&apos;t change your own roles. Ask another administrator.</p>}
          <div className="space-y-2">
            {rows.map((row, i) => {
              const role = roles.find((r) => r.id === row.role_id);
              return (
                <div key={i} className="grid grid-cols-[1fr_1fr_auto] items-start gap-2">
                  <div>
                    <Select value={row.role_id} disabled={isSelf}
                      onChange={(e) => setRows(rows.map((r, j) => (j === i ? { ...r, role_id: e.target.value } : r)))}>
                      <option value="">Select a role…</option>
                      {roles.map((r) => <option key={r.id} value={r.id}>{r.name} ({r.permission_count})</option>)}
                    </Select>
                    {role && <p className="mt-1 text-[11px] text-slate-400">{role.description}</p>}
                  </div>
                  <Select value={row.location_id} disabled={isSelf}
                    onChange={(e) => setRows(rows.map((r, j) => (j === i ? { ...r, location_id: e.target.value } : r)))}>
                    <option value="">All locations</option>
                    {me.locations.map((l) => <option key={l.id} value={l.id}>Only {l.name}</option>)}
                  </Select>
                  <Button variant="ghost" aria-label="Remove role" disabled={isSelf || rows.length === 1}
                    onClick={() => setRows(rows.filter((_, j) => j !== i))}><Trash2 className="h-4 w-4" /></Button>
                </div>
              );
            })}
          </div>
          <p className="mt-2 text-[11px] text-slate-400">You can only grant roles whose permissions you hold yourself.</p>
        </div>
      </div>
    </Dialog>
  );
}
