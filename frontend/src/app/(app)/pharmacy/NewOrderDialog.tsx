"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Trash2, UserPlus } from "lucide-react";
import { useState } from "react";
import { ItemPicker } from "@/components/ItemPicker";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/components/ui/cn";
import { Dialog } from "@/components/ui/dialog";
import { ErrorBanner, Field, Input, Select, Textarea } from "@/components/ui/form";
import { Table, Td, Th } from "@/components/ui/table";
import { useToast } from "@/components/ui/toast";
import { ApiError, errorMessage, useApi } from "@/lib/api/client";
import type { Item, Order, OrderCreate, Patient } from "@/lib/api/types";
import { useMe } from "@/lib/auth/MeProvider";
import { money } from "@/lib/format";

type Line = { item: Item; qty: number };
type Requester = { id: string; display_name: string; department: string | null };

export function NewOrderDialog({ channel, onClose }: { channel: "counter_sale" | "requisition"; onClose: () => void }) {
  const api = useApi();
  const qc = useQueryClient();
  const toast = useToast();
  const { me, can } = useMe();
  const isSale = channel === "counter_sale";
  const pharmacyStaff = can("pharmacy_order:create");

  const [lines, setLines] = useState<Line[]>([]);
  const [buyer, setBuyer] = useState<"patient" | "walk_in">("patient");
  const [patient, setPatient] = useState<Patient | null>(null);
  const [walkIn, setWalkIn] = useState({ name: "", phone: "" });
  const [rx, setRx] = useState({ ref: "", prescriber: "" });
  const [req, setReq] = useState({ requested_by_id: "", department: pharmacyStaff ? "" : me.user.department ?? "", surgery_ref: "" });
  const [notes, setNotes] = useState("");

  const requesters = useQuery({
    queryKey: ["requesters"], enabled: !isSale && pharmacyStaff,
    queryFn: () => api<Requester[]>("/pharmacy/requesters"),
  });
  // Doctors/nurses always request in their own name; pharmacists pick the requesting clinician.
  const requestedBy = pharmacyStaff ? req.requested_by_id || requesters.data?.[0]?.id || "" : me.user.id;

  const needsRx = isSale && lines.some((l) => l.item.schedule !== "none");
  const needsPrescriber = isSale && lines.some((l) => l.item.schedule === "H1" || l.item.schedule === "X");
  const total = lines.reduce((s, l) => s + l.qty * Number(l.item.mrp), 0);

  const create = useMutation({
    mutationFn: () => {
      const body: OrderCreate = {
        channel,
        lines: lines.map((l) => ({ item_id: l.item.id, qty: l.qty })),
        notes: notes || null,
        ...(isSale
          ? {
              patient_id: buyer === "patient" ? patient?.id ?? null : null,
              walk_in_name: buyer === "walk_in" ? walkIn.name : null,
              walk_in_phone: buyer === "walk_in" ? walkIn.phone || null : null,
              prescription_ref: rx.ref || null,
              prescriber_name: rx.prescriber || null,
            }
          : { requested_by_id: requestedBy, department: req.department, surgery_ref: req.surgery_ref || null }),
      };
      return api<Order>("/pharmacy/orders", { method: "POST", body });
    },
    onSuccess: (o) => {
      toast("success", `${o.order_no} created · stock reserved by FEFO`);
      ["pharmacy-orders", "dashboard", "batches", "items"].forEach((k) => qc.invalidateQueries({ queryKey: [k] }));
      onClose();
    },
  });

  const valid = lines.length > 0 && lines.every((l) => l.qty > 0) && (isSale
    ? (buyer === "patient" ? !!patient : walkIn.name.trim().length > 1) && (!needsRx || rx.ref.trim()) && (!needsPrescriber || rx.prescriber.trim())
    : req.department.trim().length > 1 && !!requestedBy);

  const shortages = create.error instanceof ApiError && create.error.code === "INSUFFICIENT_STOCK"
    ? (create.error.body.shortages as { item_id: string; available: number }[]) : [];

  return (
    <Dialog open onClose={onClose} size="xl"
      title={isSale ? "New counter sale" : "New pharmacy requisition"}
      description={isSale ? "Sell to a registered patient or a walk-in buyer. Stock is reserved first-expiry-first-out."
        : "Request stock from the pharmacy for a doctor, OT list or ward. The pharmacist dispatches it."}
      footer={<div className="flex w-full items-center justify-between">
        <span className="text-sm text-slate-500">{lines.length} item(s) · <b className="text-slate-900">{money(total)}</b> {isSale && <span className="text-xs">(MRP incl. GST)</span>}</span>
        <div className="flex gap-2"><Button onClick={onClose}>Cancel</Button>
          <Button variant="primary" disabled={!valid} loading={create.isPending} onClick={() => create.mutate()}>{isSale ? "Create sale & allocate" : "Submit requisition"}</Button></div>
      </div>}>
      <div className="space-y-5">
        <ErrorBanner message={create.error ? errorMessage(create.error) : null} />

        {isSale ? (
          <div className="space-y-3">
            <div className="inline-flex rounded-lg border border-slate-200 p-0.5">
              {(["patient", "walk_in"] as const).map((b) => (
                <button key={b} onClick={() => setBuyer(b)} className={cn("rounded-md px-3 py-1.5 text-sm font-medium",
                  buyer === b ? "bg-ink text-white" : "text-slate-600")}>{b === "patient" ? "Registered patient" : "Walk-in buyer"}</button>
              ))}
            </div>
            {buyer === "patient"
              ? <PatientPicker value={patient} onChange={setPatient} />
              : <div className="grid gap-3 sm:grid-cols-2">
                  <Field label="Buyer name" required><Input value={walkIn.name} onChange={(e) => setWalkIn({ ...walkIn, name: e.target.value })} /></Field>
                  <Field label="Phone"><Input value={walkIn.phone} onChange={(e) => setWalkIn({ ...walkIn, phone: e.target.value })} /></Field>
                </div>}
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Prescription reference" required={needsRx} hint={needsRx ? "Required: basket contains Schedule H/H1/X items" : "Optional for OTC items"}>
                <Input value={rx.ref} onChange={(e) => setRx({ ...rx, ref: e.target.value })} placeholder="e.g. OPD-RX-55120" /></Field>
              <Field label="Prescriber" required={needsPrescriber} hint={needsPrescriber ? "Required for the Schedule H1 register" : undefined}>
                <Input value={rx.prescriber} onChange={(e) => setRx({ ...rx, prescriber: e.target.value })} placeholder="Dr. …" /></Field>
            </div>
          </div>
        ) : (
          <div className="grid gap-3 sm:grid-cols-3">
            <Field label="Requested by" required>
              {pharmacyStaff
                ? <Select value={requestedBy} onChange={(e) => {
                    const r = requesters.data?.find((x) => x.id === e.target.value);
                    setReq({ ...req, requested_by_id: e.target.value, department: r?.department ?? req.department });
                  }}>
                    {requesters.data?.map((r) => <option key={r.id} value={r.id}>{r.display_name}</option>)}
                  </Select>
                : <Input value={me.user.display_name} disabled />}
            </Field>
            <Field label="Department / OT" required><Input value={req.department} onChange={(e) => setReq({ ...req, department: e.target.value })} placeholder="e.g. OT-1 (Cataract)" /></Field>
            <Field label="Surgery / OT list reference"><Input value={req.surgery_ref} onChange={(e) => setReq({ ...req, surgery_ref: e.target.value })} placeholder="e.g. Phaco list 08:30" /></Field>
          </div>
        )}

        <div>
          <p className="mb-2 text-xs font-medium text-slate-700">Items</p>
          <ItemPicker dispensable exclude={lines.map((l) => l.item.id)} onPick={(item) => setLines([...lines, { item, qty: 1 }])} />
          {lines.length > 0 && (
            <div className="mt-3 overflow-hidden rounded-xl border border-slate-200">
              <Table className="min-w-0">
                <thead><tr><Th>Item</Th><Th>Available</Th><Th className="w-28">Qty</Th><Th className="text-right">MRP</Th><Th className="text-right">Amount</Th><Th /></tr></thead>
                <tbody>
                  {lines.map((l, i) => {
                    const short = shortages.find((s) => s.item_id === l.item.id);
                    return (
                      <tr key={l.item.id}>
                        <Td>
                          <p className="font-medium">{l.item.name}</p>
                          <p className="text-[11px] text-slate-400">{l.item.sku} {l.item.schedule !== "none" && <Badge tone="violet" className="ml-1">Sch {l.item.schedule}</Badge>}</p>
                        </Td>
                        <Td className={l.qty > l.item.available || short ? "text-rose-600" : "text-slate-600"}>
                          {short ? <span className="flex items-center gap-1"><AlertTriangle className="h-3.5 w-3.5" />{short.available} in-date</span> : l.item.available}
                        </Td>
                        <Td><Input type="number" min={1} value={l.qty} onChange={(e) => setLines(lines.map((x, j) => (j === i ? { ...x, qty: Math.max(1, Number(e.target.value)) } : x)))} /></Td>
                        <Td className="text-right">{money(l.item.mrp)}</Td>
                        <Td className="text-right font-medium">{money(l.qty * Number(l.item.mrp))}</Td>
                        <Td><Button size="sm" variant="ghost" aria-label="Remove" onClick={() => setLines(lines.filter((_, j) => j !== i))}><Trash2 className="h-4 w-4" /></Button></Td>
                      </tr>
                    );
                  })}
                </tbody>
              </Table>
            </div>
          )}
          <p className="mt-2 text-[11px] text-slate-400">
            &quot;Available&quot; is across your locations; the pharmacy only dispenses its own in-date stock with at least 30 days of shelf life.
          </p>
        </div>
        <Field label="Notes"><Textarea value={notes} onChange={(e) => setNotes(e.target.value)} className="min-h-14" /></Field>
      </div>
    </Dialog>
  );
}

function PatientPicker({ value, onChange }: { value: Patient | null; onChange: (p: Patient | null) => void }) {
  const api = useApi();
  const { can } = useMe();
  const [q, setQ] = useState("");
  const [registering, setRegistering] = useState(false);
  const [np, setNp] = useState({ mrn: "", name: "", phone: "", age: "", gender: "" });
  const results = useQuery({
    queryKey: ["patients", q], enabled: q.trim().length >= 2,
    queryFn: () => api<Patient[]>("/patients", { query: { q } }),
  });
  const register = useMutation({
    mutationFn: () => api<Patient>("/patients", { method: "POST", body: { mrn: np.mrn, name: np.name, phone: np.phone || null,
      age: np.age ? Number(np.age) : null, gender: np.gender || null } }),
    onSuccess: (p) => { onChange(p); setRegistering(false); },
  });
  if (value) {
    return (
      <div className="flex items-center justify-between rounded-lg border border-slate-200 px-3 py-2 text-sm">
        <span><b>{value.name}</b> <span className="font-mono text-xs text-slate-500">{value.mrn}</span>{value.phone && <span className="text-slate-400"> · {value.phone}</span>}</span>
        <Button size="sm" variant="ghost" onClick={() => onChange(null)}>Change</Button>
      </div>
    );
  }
  if (registering) {
    return (
      <div className="space-y-3 rounded-xl border border-slate-200 p-3">
        <ErrorBanner message={register.error ? errorMessage(register.error) : null} />
        <div className="grid gap-3 sm:grid-cols-5">
          <Field label="MRN" required><Input value={np.mrn} onChange={(e) => setNp({ ...np, mrn: e.target.value })} /></Field>
          <Field label="Name" required className="sm:col-span-2"><Input value={np.name} onChange={(e) => setNp({ ...np, name: e.target.value })} /></Field>
          <Field label="Phone"><Input value={np.phone} onChange={(e) => setNp({ ...np, phone: e.target.value })} /></Field>
          <Field label="Age"><Input type="number" value={np.age} onChange={(e) => setNp({ ...np, age: e.target.value })} /></Field>
        </div>
        <div className="flex justify-end gap-2"><Button size="sm" onClick={() => setRegistering(false)}>Back</Button>
          <Button size="sm" variant="primary" loading={register.isPending} disabled={np.mrn.length < 2 || np.name.length < 2} onClick={() => register.mutate()}>Register patient</Button></div>
      </div>
    );
  }
  return (
    <div className="space-y-2">
      <div className="flex gap-2">
        <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search patient by name, MRN or phone…" />
        {can("patient:manage") && <Button icon={<UserPlus className="h-4 w-4" />} onClick={() => setRegistering(true)}>New</Button>}
      </div>
      {results.data && (
        <ul className="max-h-48 overflow-y-auto rounded-xl border border-slate-200 p-1">
          {results.data.length === 0 && <li className="px-3 py-2 text-xs text-slate-400">No patients found</li>}
          {results.data.map((p) => (
            <li key={p.id}><button onClick={() => onChange(p)} className="w-full rounded-lg px-3 py-2 text-left text-sm hover:bg-slate-50">
              <b>{p.name}</b> <span className="font-mono text-xs text-slate-500">{p.mrn}</span>
              <span className="text-xs text-slate-400"> · {[p.age && `${p.age}y`, p.gender, p.phone].filter(Boolean).join(" · ")}</span>
            </button></li>
          ))}
        </ul>
      )}
    </div>
  );
}
