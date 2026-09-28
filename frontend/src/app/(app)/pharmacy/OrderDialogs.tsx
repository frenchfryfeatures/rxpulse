"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Printer } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { ConfirmDialog, Dialog } from "@/components/ui/dialog";
import { ErrorBanner, Field, Input } from "@/components/ui/form";
import { Table, Td, Th } from "@/components/ui/table";
import { useToast } from "@/components/ui/toast";
import { errorMessage, useApi } from "@/lib/api/client";
import type { Order, PickList } from "@/lib/api/types";
import { dateOnly, dateTime, money } from "@/lib/format";
import { StatusBadge } from "./status";

function useOrderAction(path: (o: Order) => string, success: (o: Order) => string, onClose: () => void) {
  const api = useApi();
  const qc = useQueryClient();
  const toast = useToast();
  return useMutation({
    mutationFn: ({ order, body }: { order: Order; body?: unknown }) => api<Order>(path(order), { method: "POST", body }),
    onSuccess: (o) => {
      toast("success", success(o));
      ["pharmacy-orders", "dashboard", "batches", "items"].forEach((k) => qc.invalidateQueries({ queryKey: [k] }));
      onClose();
    },
  });
}

function Lines({ order }: { order: Order }) {
  return (
    <div className="overflow-hidden rounded-xl border border-slate-200">
      <Table className="min-w-0">
        <thead><tr><Th>#</Th><Th>Item</Th><Th>Batches (FEFO)</Th><Th className="text-right">Qty</Th><Th className="text-right">Amount</Th></tr></thead>
        <tbody>
          {order.lines.map((l) => (
            <tr key={l.id}>
              <Td>{l.line_no}</Td>
              <Td><p className="font-medium">{l.item_name}</p><p className="font-mono text-[11px] text-slate-400">{l.sku}{l.schedule !== "none" && ` · Sch ${l.schedule}`}</p></Td>
              <Td className="text-xs">{l.allocations.map((a) => <p key={a.batch_id}>{a.batch_no} · exp {dateOnly(a.expiry_date)} · {a.qty}u{a.qty_returned > 0 && <span className="text-amber-600"> ({a.qty_returned} returned)</span>}</p>)}</Td>
              <Td className="text-right">{l.qty}</Td>
              <Td className="text-right font-medium">{money(l.line_total)}</Td>
            </tr>
          ))}
        </tbody>
      </Table>
      <div className="space-y-0.5 border-t border-slate-100 bg-slate-50/60 px-4 py-3 text-right text-sm">
        <p className="text-slate-500">Taxable value {money(order.subtotal)} · GST {money(order.gst_amount)}</p>
        <p className="text-base font-bold">Total {money(order.total)}</p>
      </div>
    </div>
  );
}

export function OrderDetailDialog({ order, onClose }: { order: Order; onClose: () => void }) {
  return (
    <Dialog open onClose={onClose} size="lg" title={<span className="flex items-center gap-3">{order.order_no}<StatusBadge status={order.status} /></span>}
      description={`${order.channel === "counter_sale" ? "Counter sale" : "Requisition"} · ${order.location_name} · created ${dateTime(order.created_at)} by ${order.created_by_name}`}>
      <dl className="mb-4 grid gap-x-6 gap-y-2 text-sm sm:grid-cols-2">
        <Row k={order.channel === "counter_sale" ? "Customer" : "Requested by"} v={order.party_name} />
        {order.walk_in_phone && <Row k="Phone" v={order.walk_in_phone} />}
        {order.prescription_ref && <Row k="Prescription" v={`${order.prescription_ref}${order.prescriber_name ? ` · ${order.prescriber_name}` : ""}`} />}
        {order.surgery_ref && <Row k="Surgery / OT list" v={order.surgery_ref} />}
        {order.invoice_no && <Row k="Invoice" v={order.invoice_no} />}
        {order.dispatched_at && <Row k="Dispatched" v={dateTime(order.dispatched_at)} />}
        {order.notes && <Row k="Notes" v={order.notes} />}
      </dl>
      <Lines order={order} />
    </Dialog>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return <div><dt className="text-[11px] text-slate-400">{k}</dt><dd className="font-medium text-slate-800">{v}</dd></div>;
}

export function PickListDialog({ order, onClose }: { order: Order; onClose: () => void }) {
  const api = useApi();
  const pick = useQuery({ queryKey: ["pick-list", order.id], queryFn: () => api<PickList>(`/pharmacy/orders/${order.id}/pick-list`) });
  return (
    <Dialog open onClose={onClose} size="lg" title={`Pick list · ${order.order_no}`} description={`${order.location_name} · ${order.party_name}`}
      footer={<><Button onClick={onClose}>Close</Button><Button variant="primary" icon={<Printer className="h-4 w-4" />} onClick={() => printPickList(pick.data)} disabled={!pick.data}>Print</Button></>}>
      <div className="overflow-hidden rounded-xl border border-slate-200">
        <Table className="min-w-0">
          <thead><tr><Th>Bin</Th><Th>Item</Th><Th>Batch</Th><Th>Expiry</Th><Th className="text-right">Qty</Th><Th>✓</Th></tr></thead>
          <tbody>
            {pick.data?.rows.map((r, i) => (
              <tr key={i}><Td className="font-mono text-xs font-semibold">{r.bin_code ?? "—"}</Td><Td>{r.item_name}</Td>
                <Td className="font-mono text-xs">{r.batch_no}</Td><Td>{dateOnly(r.expiry_date)}</Td><Td className="text-right font-bold">{r.qty}</Td>
                <Td><span className="inline-block h-4 w-4 rounded border border-slate-300" /></Td></tr>
            ))}
          </tbody>
        </Table>
      </div>
      <p className="mt-3 text-xs text-slate-500">Pick exactly these batches. They were allocated first-expiry-first-out, and the stock is reserved until dispatch.</p>
    </Dialog>
  );
}

function printPickList(p?: PickList) {
  if (!p) return;
  const w = window.open("", "_blank", "width=800,height=600");
  if (!w) return;
  const esc = (s: string) => s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]!);
  w.document.write(`<html><head><title>Pick list ${esc(p.order_no)}</title><style>
    body{font-family:system-ui,sans-serif;padding:24px}table{width:100%;border-collapse:collapse}
    th,td{border:1px solid #ccc;padding:6px;text-align:left;font-size:13px}</style></head><body>
    <h2>Pick list ${esc(p.order_no)}</h2><p>${esc(p.location_name)} · ${esc(p.party_name)}</p>
    <table><tr><th>Bin</th><th>Item</th><th>Batch</th><th>Expiry</th><th>Qty</th><th>Picked</th></tr>
    ${p.rows.map((r) => `<tr><td>${esc(r.bin_code ?? "")}</td><td>${esc(r.item_name)}</td><td>${esc(r.batch_no)}</td><td>${esc(dateOnly(r.expiry_date))}</td><td>${r.qty}</td><td></td></tr>`).join("")}
    </table><p style="margin-top:32px">Picked by: ____________ Checked by: ____________</p></body></html>`);
  w.document.close();
  w.print();
}

export function DispatchDialog({ order, onClose }: { order: Order; onClose: () => void }) {
  const m = useOrderAction((o) => `/pharmacy/orders/${o.id}/dispatch`,
    (o) => (o.invoice_no ? `Dispatched · invoice ${o.invoice_no}` : `${o.order_no} dispatched`), onClose);
  return (
    <ConfirmDialog open onClose={onClose} onConfirm={() => m.mutate({ order })} loading={m.isPending}
      error={m.error ? errorMessage(m.error) : null} title={`Dispatch ${order.order_no}?`} confirmLabel="Confirm dispatch">
      <p>Hand over to <b>{order.party_name}</b>. {order.lines.length} line(s), total <b>{money(order.total)}</b>.</p>
      <ul className="list-disc space-y-0.5 pl-5 text-xs">
        {order.lines.map((l) => <li key={l.id}>{l.qty} × {l.item_name} ({l.allocations.map((a) => a.batch_no).join(", ")})</li>)}
      </ul>
      <p className="text-xs text-slate-500">
        Stock is deducted from the reserved batches.{order.channel === "counter_sale" ? " A GST invoice number is issued." : " Charged internally to the department."}
      </p>
    </ConfirmDialog>
  );
}

export function CancelDialog({ order, onClose }: { order: Order; onClose: () => void }) {
  const m = useOrderAction((o) => `/pharmacy/orders/${o.id}/cancel`, (o) => `${o.order_no} cancelled`, onClose);
  return (
    <ConfirmDialog open onClose={onClose} onConfirm={() => m.mutate({ order })} loading={m.isPending} tone="danger"
      error={m.error ? errorMessage(m.error) : null} title={`Cancel ${order.order_no}?`} confirmLabel="Cancel order">
      <p>The reserved stock is released back to the pharmacy. This can&apos;t be undone.</p>
    </ConfirmDialog>
  );
}

export function ReturnDialog({ order, onClose }: { order: Order; onClose: () => void }) {
  const m = useOrderAction((o) => `/pharmacy/orders/${o.id}/return`, (o) => `Return recorded for ${o.order_no}`, onClose);
  const [qty, setQty] = useState<Record<string, number>>({});
  const [reason, setReason] = useState("");
  const lines = order.lines.map((l) => ({ ...l, outstanding: l.qty - l.qty_returned })).filter((l) => l.outstanding > 0);
  const payload = Object.entries(qty).filter(([, v]) => v > 0).map(([line_id, v]) => ({ line_id, qty: v }));
  const refund = lines.reduce((s, l) => s + (qty[l.id] ?? 0) * Number(l.unit_price), 0);
  return (
    <Dialog open onClose={onClose} size="lg" title={`Return against ${order.order_no}`} description="Returned units go back into the batch they came from."
      footer={<><Button onClick={onClose}>Cancel</Button><Button variant="primary" loading={m.isPending}
        disabled={payload.length === 0 || reason.trim().length < 3} onClick={() => m.mutate({ order, body: { lines: payload, reason } })}>Record return</Button></>}>
      <div className="space-y-4">
        <ErrorBanner message={m.error ? errorMessage(m.error) : null} />
        <div className="overflow-hidden rounded-xl border border-slate-200">
          <Table className="min-w-0">
            <thead><tr><Th>Item</Th><Th className="text-right">Dispatched</Th><Th className="text-right">Already returned</Th><Th className="w-32">Return qty</Th></tr></thead>
            <tbody>
              {lines.map((l) => (
                <tr key={l.id}><Td>{l.item_name}</Td><Td className="text-right">{l.qty}</Td><Td className="text-right">{l.qty_returned}</Td>
                  <Td><Input type="number" min={0} max={l.outstanding} value={qty[l.id] ?? 0}
                    onChange={(e) => setQty({ ...qty, [l.id]: Math.min(l.outstanding, Math.max(0, Number(e.target.value))) })} /></Td></tr>
              ))}
            </tbody>
          </Table>
        </div>
        <Field label="Reason" required><Input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. Patient discontinued, unopened" /></Field>
        {order.channel === "counter_sale" && refund > 0 && <p className="text-sm">Refund due to customer: <b>{money(refund)}</b></p>}
      </div>
    </Dialog>
  );
}
