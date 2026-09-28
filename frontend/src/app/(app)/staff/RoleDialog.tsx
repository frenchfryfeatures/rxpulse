"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Lock, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { cn } from "@/components/ui/cn";
import { ConfirmDialog, Dialog } from "@/components/ui/dialog";
import { ErrorBanner, Field, Input } from "@/components/ui/form";
import { useToast } from "@/components/ui/toast";
import { errorMessage, useApi } from "@/lib/api/client";
import type { Permission, Role } from "@/lib/api/types";
import { useMe } from "@/lib/auth/MeProvider";

export function RoleDialog({ role, onClose }: { role: Role | null; onClose: () => void }) {
  const api = useApi();
  const qc = useQueryClient();
  const toast = useToast();
  const { can } = useMe();
  const editable = can("role:manage") && !role?.is_immutable;
  const [name, setName] = useState(role?.name ?? "");
  const [description, setDescription] = useState(role?.description ?? "");
  const [selected, setSelected] = useState<Set<string>>(new Set(role?.permissions ?? []));
  const [confirmDelete, setConfirmDelete] = useState(false);

  const perms = useQuery({ queryKey: ["permissions"], queryFn: () => api<Permission[]>("/permissions") });
  const modules = useMemo(() => {
    const m = new Map<string, Permission[]>();
    for (const p of perms.data ?? []) m.set(p.module, [...(m.get(p.module) ?? []), p]);
    return [...m.entries()];
  }, [perms.data]);

  const done = (msg: string) => {
    toast("success", msg);
    qc.invalidateQueries({ queryKey: ["roles"] });
    qc.invalidateQueries({ queryKey: ["me"] });
    onClose();
  };

  const save = useMutation({
    mutationFn: async () => {
      const permissions = [...selected].sort();
      if (!role) return api<Role>("/roles", { method: "POST", body: { name, description, permissions } });
      if (name !== role.name || description !== role.description) {
        await api<Role>(`/roles/${role.id}`, { method: "PATCH", body: role.is_system ? { description } : { name, description } });
      }
      return api<Role>(`/roles/${role.id}/permissions`, { method: "PUT", body: { permissions } });
    },
    onSuccess: () => done(role ? "Role updated" : "Role created"),
  });
  const del = useMutation({
    mutationFn: () => api(`/roles/${role!.id}`, { method: "DELETE" }),
    onSuccess: () => done("Role deleted"),
  });

  const toggle = (code: string) => {
    const next = new Set(selected);
    if (next.has(code)) next.delete(code); else next.add(code);
    setSelected(next);
  };
  const toggleModule = (list: Permission[]) => {
    const next = new Set(selected);
    const all = list.every((p) => next.has(p.code));
    list.forEach((p) => (all ? next.delete(p.code) : next.add(p.code)));
    setSelected(next);
  };

  return (
    <>
      <Dialog open onClose={onClose} size="xl"
        title={<span className="flex items-center gap-2">{role ? role.name : "New custom role"}{role?.is_immutable && <Lock className="h-4 w-4 text-slate-400" />}</span>}
        description={role?.is_immutable ? "Super Admin always holds every permission and cannot be changed."
          : role?.is_system ? "System role: permissions can be tuned for your hospital, but it can't be renamed or deleted."
            : "Choose exactly what this role can see and do."}
        footer={editable ? (
          <div className="flex w-full items-center justify-between">
            <div>{role && !role.is_system && (
              <Button variant="outline-danger" icon={<Trash2 className="h-4 w-4" />} onClick={() => setConfirmDelete(true)}>Delete role</Button>)}</div>
            <div className="flex gap-2">
              <Button onClick={onClose}>Cancel</Button>
              <Button variant="primary" loading={save.isPending} disabled={name.trim().length < 2} onClick={() => save.mutate()}>
                {role ? "Save role" : "Create role"}
              </Button>
            </div>
          </div>
        ) : <Button onClick={onClose}>Close</Button>}>
        <div className="space-y-5">
          <ErrorBanner message={save.error ? errorMessage(save.error) : null} />
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Role name" required><Input value={name} disabled={!editable || role?.is_system} onChange={(e) => setName(e.target.value)} /></Field>
            <Field label="Description"><Input value={description} disabled={!editable} onChange={(e) => setDescription(e.target.value)} /></Field>
          </div>
          <div className="flex items-center justify-between">
            <p className="text-xs font-medium text-slate-700">Permissions</p>
            <p className="text-xs text-slate-500"><b>{selected.size}</b> of {perms.data?.length ?? "…"} selected</p>
          </div>
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {modules.map(([module, list]) => {
              const count = list.filter((p) => selected.has(p.code)).length;
              return (
                <div key={module} className="rounded-xl border border-slate-200">
                  <label className="flex items-center justify-between gap-2 border-b border-slate-100 bg-slate-50/70 px-3 py-2">
                    <span className="text-xs font-semibold tracking-wide text-slate-700 uppercase">{module}</span>
                    <span className="flex items-center gap-2 text-[11px] text-slate-400">{count}/{list.length}
                      <input type="checkbox" disabled={!editable} checked={count === list.length}
                        ref={(el) => { if (el) el.indeterminate = count > 0 && count < list.length; }}
                        onChange={() => toggleModule(list)} aria-label={`Toggle all ${module} permissions`} />
                    </span>
                  </label>
                  <div className="space-y-1 p-2">
                    {list.map((p) => (
                      <label key={p.code} className={cn("flex items-start gap-2 rounded-md px-1.5 py-1 text-xs", editable && "cursor-pointer hover:bg-slate-50")}>
                        <input type="checkbox" className="mt-0.5" disabled={!editable} checked={selected.has(p.code)} onChange={() => toggle(p.code)} />
                        <span><span className="block text-slate-700">{p.description}</span>
                          <span className="font-mono text-[10px] text-slate-400">{p.code}</span></span>
                      </label>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
          {editable && <p className="text-[11px] text-slate-400">You can only add or remove permissions that you hold yourself.</p>}
        </div>
      </Dialog>
      <ConfirmDialog open={confirmDelete} onClose={() => { setConfirmDelete(false); del.reset(); }} onConfirm={() => del.mutate()}
        loading={del.isPending} error={del.error ? errorMessage(del.error) : null} tone="danger" title="Delete role?" confirmLabel="Delete">
        <p>The <b>{role?.name}</b> role will be permanently removed. Roles still assigned to staff can&apos;t be deleted.</p>
      </ConfirmDialog>
    </>
  );
}
