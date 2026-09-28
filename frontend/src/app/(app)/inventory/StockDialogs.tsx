"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { ItemPicker } from "@/components/ItemPicker";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { ErrorBanner, Field, Input, Select } from "@/components/ui/form";
import { Table, Td, Th } from "@/components/ui/table";
import { useToast } from "@/components/ui/toast";
import { errorMessage, useApi } from "@/lib/api/client";
import type { BatchRow, Item, Ledger } from "@/lib/api/types";
import { useMe } from "@/lib/auth/MeProvider";
import { dateOnly, dateTime, money } from "@/lib/format";
import { ExpiryCell, useScopedLocations } from "./shared";

function useStockMutation<T>(fn: () => Promise<T>, success: string, onClose: () => void) {
  const qc = useQueryClient();
  const toast = useToast();
  return useMutation({
    mutationFn: fn,
    onSuccess: () => {
      toast("success", success);
      ["batches", "dashboard", "expiry-risk", "movements", "items"].forEach((k) => qc.invalidateQueries({ queryKey: [k] }));
      onClose();
    },
  });
}

const REASONS: Record<string, string> = {
  receipt: "Receipt", adjustment: "Adjustment", transfer_out: "Transfer out", transfer_in: "Transfer in",
  issue: "Dispatched", return_in: "Returned", writeoff: "Write-off",
};

export function LedgerDialog({ row, onClose }: { row: BatchRow; onClose: () => void }) {
  const api = useApi();
  const ledger = useQuery({ queryKey: ["ledger", row.batch_id], queryFn: () => api<Ledger[]>(`/batches/${row.batch_id}/ledger`) });
  return (
    <Dialog open onClose={onClose} size="lg" title={`${row.item_name} · ${row.batch_no}`} description={`${row.location_name}${row.bin_code ? ` · Bin ${row.bin_code}` : ""}`}>
      <div className="grid gap-3 sm:grid-cols-4">
        <Stat label="On hand" value={`${row.qty_on_hand} units`} />
        <Stat label="Reserved" value={`${row.qty_reserved} units`} />
        <Stat label="Unit cost / MRP" value={`${money(row.unit_cost)} / ${money(row.mrp)}`} />
        <div className="rounded-xl border border-slate-200 p-3"><p className="text-[11px] text-slate-500">Expiry</p><ExpiryCell row={row} /></div>
      </div>
      <h3 className="mt-5 mb-2 text-xs font-semibold tracking-wider text-slate-500 uppercase">Movement history</h3>
      <div className="max-h-80 overflow-y-auto rounded-xl border border-slate-200">
        <Table className="min-w-0">
          <thead><tr><Th>When</Th><Th>Movement</Th><Th>Location</Th><Th className="text-right">Qty</Th><Th>By / note</Th></tr></thead>
          <tbody>
            {ledger.data?.map((l) => (
              <tr key={l.id}>
                <Td className="text-xs">{dateTime(l.created_at)}</Td>
                <Td><Badge tone={l.qty_delta > 0 ? "green" : "slate"} uppercase={false}>{REASONS[l.reason] ?? l.reason}</Badge></Td>
                <Td className="text-xs">{l.location_name}</Td>
                <Td className={`text-right font-mono ${l.qty_delta > 0 ? "text-emerald-600" : "text-rose-600"}`}>{l.qty_delta > 0 ? "+" : ""}{l.qty_delta}</Td>
                <Td className="text-xs text-slate-500">{l.actor_name ?? "System"}{l.note && <span className="block text-slate-400">{l.note}</span>}</Td>
              </tr>
            ))}
          </tbody>
        </Table>
      </div>
    </Dialog>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return <div className="rounded-xl border border-slate-200 p-3"><p className="text-[11px] text-slate-500">{label}</p><p className="font-semibold text-slate-900">{value}</p></div>;
}

export function AdjustDialog({ row, onClose }: { row: BatchRow; onClose: () => void }) {
  const api = useApi();
  const { can } = useMe();
  const [direction, setDirection] = useState<"out" | "in">("out");
  const [qty, setQty] = useState(1);
  const [reason, setReason] = useState("count_correction");
  const [note, setNote] = useState("");
  const delta = direction === "out" ? -qty : qty;
  const isWriteoff = delta < 0 && (reason === "damaged" || reason === "expired");
  const m = useStockMutation(
    () => api("/stock/adjustments", { method: "POST", body: { batch_id: row.batch_id, location_id: row.location_id, qty_delta: delta, reason, note } }),
    "Stock adjusted", onClose);
  return (
    <Dialog open onClose={onClose} title="Adjust stock" description={`${row.item_name} · ${row.batch_no} · ${row.location_name}`}
      footer={<><Button onClick={onClose}>Cancel</Button><Button variant="primary" loading={m.isPending}
        disabled={qty < 1 || note.trim().length < 3 || (isWriteoff && !can("inventory:writeoff", row.location_id))} onClick={() => m.mutate()}>
        {isWriteoff ? "Write off" : "Post adjustment"}</Button></>}>
      <div className="space-y-4">
        <ErrorBanner message={m.error ? errorMessage(m.error) : null} />
        <div className="grid gap-4 sm:grid-cols-3">
          <Field label="Direction"><Select value={direction} onChange={(e) => setDirection(e.target.value as "in" | "out")}>
            <option value="out">Remove (−)</option><option value="in">Add (+)</option></Select></Field>
          <Field label="Quantity" hint={`${row.qty_available} unreserved`}><Input type="number" min={1} value={qty} onChange={(e) => setQty(Number(e.target.value))} /></Field>
          <Field label="Reason"><Select value={reason} onChange={(e) => setReason(e.target.value)}>
            <option value="count_correction">Physical count correction</option><option value="damaged">Damaged / broken</option>
            <option value="expired">Expired</option><option value="other">Other</option></Select></Field>
        </div>
        <Field label="Note" required hint="Recorded in the stock ledger and audit trail">
          <Input value={note} onChange={(e) => setNote(e.target.value)} placeholder="e.g. Cycle count 28 Sep, 2 vials cracked" /></Field>
        {isWriteoff && <p className="rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-700">This is a write-off and requires the <b>inventory:writeoff</b> permission.</p>}
        <p className="text-sm text-slate-600">New on-hand quantity: <b>{row.qty_on_hand + delta}</b></p>
      </div>
    </Dialog>
  );
}

export function TransferDialog({ row, onClose }: { row: BatchRow; onClose: () => void }) {
  const api = useApi();
  const targets = useScopedLocations("inventory:transfer").filter((l) => l.id !== row.location_id);
  const [to, setTo] = useState(targets[0]?.id ?? "");
  const [qty, setQty] = useState(1);
  const [note, setNote] = useState("");
  const m = useStockMutation(
    () => api("/stock/transfers", { method: "POST", body: { batch_id: row.batch_id, from_location_id: row.location_id, to_location_id: to, qty, note: note || null } }),
    "Stock transferred", onClose);
  return (
    <Dialog open onClose={onClose} title="Transfer stock" description={`${row.item_name} · ${row.batch_no}`}
      footer={<><Button onClick={onClose}>Cancel</Button><Button variant="primary" loading={m.isPending} disabled={!to || qty < 1 || qty > row.qty_available} onClick={() => m.mutate()}>Transfer</Button></>}>
      <div className="space-y-4">
        <ErrorBanner message={m.error ? errorMessage(m.error) : null} />
        {targets.length === 0 && <p className="text-sm text-slate-500">You can only transfer between locations in your scope, and there is no other one.</p>}
        <div className="grid gap-4 sm:grid-cols-3">
          <Field label="From"><Input value={row.location_name} disabled /></Field>
          <Field label="To"><Select value={to} onChange={(e) => setTo(e.target.value)}>{targets.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}</Select></Field>
          <Field label="Quantity" hint={`${row.qty_available} available`}><Input type="number" min={1} max={row.qty_available} value={qty} onChange={(e) => setQty(Number(e.target.value))} /></Field>
        </div>
        <Field label="Note"><Input value={note} onChange={(e) => setNote(e.target.value)} placeholder="e.g. Pharmacy top-up" /></Field>
      </div>
    </Dialog>
  );
}

export function ReceiveDialog({ onClose }: { onClose: () => void }) {
  const api = useApi();
  const locations = useScopedLocations("grn:create");
  const [item, setItem] = useState<Item | null>(null);
  const [f, setF] = useState({ location_id: locations[0]?.id ?? "", batch_no: "", expiry_date: "", mfg_date: "", qty: 1,
    unit_cost: "", mrp: "", supplier_name: "", bin_code: "" });
  const m = useStockMutation(() => api("/stock/receipts", { method: "POST", body: {
    item_id: item!.id, location_id: f.location_id, batch_no: f.batch_no.trim(), expiry_date: f.expiry_date,
    mfg_date: f.mfg_date || null, qty: f.qty, unit_cost: f.unit_cost, mrp: f.mrp || null,
    supplier_name: f.supplier_name || null, bin_code: f.bin_code || null } }), "Stock received", onClose);
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setF({ ...f, [k]: e.target.value });
  const valid = item && f.location_id && f.batch_no.trim() && f.expiry_date && f.qty > 0 && f.unit_cost !== "";
  return (
    <Dialog open onClose={onClose} size="lg" title="Receive stock (GRN)" description="Record goods received with batch and expiry details. Expired stock is rejected."
      footer={<><Button onClick={onClose}>Cancel</Button><Button variant="primary" disabled={!valid} loading={m.isPending} onClick={() => m.mutate()}>Receive</Button></>}>
      <div className="space-y-4">
        <ErrorBanner message={m.error ? errorMessage(m.error) : null} />
        <Field label="Item" required>
          {item ? (
            <div className="flex items-center justify-between rounded-lg border border-slate-200 px-3 py-2 text-sm">
              <span><b>{item.name}</b> <span className="font-mono text-xs text-slate-400">{item.sku}</span></span>
              <Button size="sm" variant="ghost" onClick={() => setItem(null)}>Change</Button>
            </div>
          ) : <ItemPicker onPick={(i) => { setItem(i); setF((x) => ({ ...x, mrp: String(i.mrp) })); }} />}
        </Field>
        <div className="grid gap-4 sm:grid-cols-3">
          <Field label="Receive into" required><Select value={f.location_id} onChange={set("location_id")}>{locations.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}</Select></Field>
          <Field label="Batch number" required><Input value={f.batch_no} onChange={set("batch_no")} /></Field>
          <Field label="Bin"><Input value={f.bin_code} onChange={set("bin_code")} placeholder="e.g. P-A1" /></Field>
          <Field label="Expiry date" required><Input type="date" value={f.expiry_date} onChange={set("expiry_date")} /></Field>
          <Field label="Manufacture date"><Input type="date" value={f.mfg_date} onChange={set("mfg_date")} /></Field>
          <Field label="Quantity" required><Input type="number" min={1} value={f.qty} onChange={(e) => setF({ ...f, qty: Number(e.target.value) })} /></Field>
          <Field label="Unit cost (₹)" required><Input type="number" min={0} step="0.01" value={f.unit_cost} onChange={set("unit_cost")} /></Field>
          <Field label="MRP (₹)"><Input type="number" min={0} step="0.01" value={f.mrp} onChange={set("mrp")} /></Field>
          <Field label="Supplier"><Input value={f.supplier_name} onChange={set("supplier_name")} /></Field>
        </div>
        {f.expiry_date && <p className="text-xs text-slate-500">Expiry {dateOnly(f.expiry_date)}</p>}
      </div>
    </Dialog>
  );
}
