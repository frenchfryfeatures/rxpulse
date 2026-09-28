"use client";

import { keepPreviousData, useMutation, useQuery } from "@tanstack/react-query";
import { ChevronDown, ChevronRight, ShieldCheck, ShieldX } from "lucide-react";
import { Fragment, useState } from "react";
import { Guard } from "@/components/auth/Guard";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, PageHeader } from "@/components/ui/card";
import { EmptyRow, FilterSelect, LoadingRows, Pagination, SearchInput, Table, Td, Th, Toolbar } from "@/components/ui/table";
import { useApi } from "@/lib/api/client";
import type { Audit, Page } from "@/lib/api/types";
import { dateTime } from "@/lib/format";

const ACTIONS = [
  { value: "", label: "All actions" }, { value: "staff", label: "Staff" }, { value: "role", label: "Roles" },
  { value: "pharmacy_order", label: "Pharmacy orders" }, { value: "stock", label: "Stock" }, { value: "item", label: "Catalogue" },
  { value: "patient", label: "Patients" },
];

export default function AuditPage() {
  return <Guard anyOf={["audit:view"]}><AuditTrail /></Guard>;
}

function AuditTrail() {
  const api = useApi();
  const [action, setAction] = useState("");
  const [actor, setActor] = useState("");
  const [page, setPage] = useState(1);
  const [open, setOpen] = useState<number | null>(null);
  const rows = useQuery({
    queryKey: ["audit", action, actor, page],
    queryFn: () => api<Page<Audit>>("/audit", { query: { action, actor, page, page_size: 25 } }),
    placeholderData: keepPreviousData,
  });
  const verify = useMutation({ mutationFn: () => api<{ ok: boolean; first_bad_id: number | null }>("/audit/verify") });

  return (
    <>
      <PageHeader title="Audit Trail" subtitle="Append-only, hash-chained record of every change: who, what, when, and before/after values."
        actions={<Button icon={<ShieldCheck className="h-4 w-4" />} loading={verify.isPending} onClick={() => verify.mutate()}>Verify integrity</Button>} />
      {verify.data && (
        <div className={`flex items-center gap-2 rounded-xl border px-4 py-3 text-sm ${verify.data.ok ? "border-emerald-200 bg-emerald-50 text-emerald-800" : "border-rose-200 bg-rose-50 text-rose-800"}`}>
          {verify.data.ok ? <ShieldCheck className="h-4 w-4" /> : <ShieldX className="h-4 w-4" />}
          {verify.data.ok ? "Hash chain verified: no audit records have been altered or removed."
            : `Tampering detected starting at record #${verify.data.first_bad_id}.`}
        </div>
      )}
      <Card className="overflow-hidden">
        <Toolbar shown={rows.data?.items.length} total={rows.data?.total} onRefresh={() => rows.refetch()} refreshing={rows.isFetching}>
          <SearchInput value={actor} onChange={(v) => { setActor(v); setPage(1); }} placeholder="Filter by user email…" />
          <FilterSelect value={action} onChange={(v) => { setAction(v); setPage(1); }} options={ACTIONS} />
        </Toolbar>
        <Table>
          <thead><tr><Th /><Th>#</Th><Th>When</Th><Th>Actor</Th><Th>Action</Th><Th>Entity</Th><Th>IP</Th></tr></thead>
          <tbody>
            {rows.isPending && <LoadingRows colSpan={7} />}
            {rows.data?.items.length === 0 && <EmptyRow colSpan={7}>No audit records.</EmptyRow>}
            {rows.data?.items.map((r) => (
              <Fragment key={r.id}>
                <tr className="cursor-pointer hover:bg-slate-50/60" onClick={() => setOpen(open === r.id ? null : r.id)}>
                  <Td className="w-8">{open === r.id ? <ChevronDown className="h-4 w-4 text-slate-400" /> : <ChevronRight className="h-4 w-4 text-slate-400" />}</Td>
                  <Td className="font-mono text-xs text-slate-400">{r.id}</Td>
                  <Td className="text-xs whitespace-nowrap">{dateTime(r.ts)}</Td>
                  <Td><p className="text-sm">{r.actor_email ?? "system"}</p><Badge tone={r.actor_type === "user" ? "slate" : "violet"} uppercase={false}>{r.actor_type}</Badge></Td>
                  <Td className="font-mono text-xs">{r.action}</Td>
                  <Td className="text-xs">{r.entity_type} <span className="font-mono text-slate-400">{r.entity_id?.slice(0, 8)}</span></Td>
                  <Td className="font-mono text-xs text-slate-400">{r.ip}</Td>
                </tr>
                {open === r.id && (
                  <tr><Td colSpan={7} className="bg-slate-50/60">
                    <div className="grid gap-3 md:grid-cols-2">
                      <Json label="Before" value={r.before} />
                      <Json label="After" value={r.after} />
                    </div>
                  </Td></tr>
                )}
              </Fragment>
            ))}
          </tbody>
        </Table>
        <Pagination page={page} pageSize={25} total={rows.data?.total ?? 0} onPage={setPage} />
      </Card>
    </>
  );
}

function Json({ label, value }: { label: string; value: unknown }) {
  return (
    <div>
      <p className="mb-1 text-[11px] font-semibold tracking-wider text-slate-500 uppercase">{label}</p>
      <pre className="max-h-64 overflow-auto rounded-lg border border-slate-200 bg-white p-3 font-mono text-[11px] text-slate-700">
        {value ? JSON.stringify(value, null, 2) : "—"}
      </pre>
    </div>
  );
}
