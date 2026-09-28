"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Snowflake } from "lucide-react";
import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { ErrorBanner, Field, Input, Select } from "@/components/ui/form";
import { EmptyRow, FilterSelect, LoadingRows, Pagination, SearchInput, Table, Td, Th, Toolbar } from "@/components/ui/table";
import { useToast } from "@/components/ui/toast";
import { errorMessage, useApi } from "@/lib/api/client";
import type { Item, ItemCreate, Page } from "@/lib/api/types";
import { useMe } from "@/lib/auth/MeProvider";
import { money } from "@/lib/format";

type TypeFilter = "all" | "drug" | "consumable" | "iol" | "equipment";

export function CatalogTab() {
  const api = useApi();
  const { can } = useMe();
  const [q, setQ] = useState("");
  const [type, setType] = useState<TypeFilter>("all");
  const [page, setPage] = useState(1);
  const [adding, setAdding] = useState(false);
  const items = useQuery({
    queryKey: ["items", q, type, page],
    queryFn: () => api<Page<Item>>("/items", { query: { q, type: type === "all" ? undefined : type, page, page_size: 25 } }),
    placeholderData: keepPreviousData,
  });
  return (
    <>
      <Toolbar shown={items.data?.items.length} total={items.data?.total} onRefresh={() => items.refetch()} refreshing={items.isFetching}>
        <SearchInput value={q} onChange={(v) => { setQ(v); setPage(1); }} placeholder="Search name, generic or SKU…" />
        <FilterSelect<TypeFilter> value={type} onChange={(v) => { setType(v); setPage(1); }} options={[
          { value: "all", label: "All types" }, { value: "drug", label: "Drugs" }, { value: "consumable", label: "Surgical consumables" },
          { value: "iol", label: "IOLs" }, { value: "equipment", label: "Equipment" }]} />
        {can("item:manage") && <Button size="sm" variant="primary" icon={<Plus className="h-3.5 w-3.5" />} onClick={() => setAdding(true)}>Add item</Button>}
      </Toolbar>
      <Table>
        <thead><tr><Th>Item</Th><Th>Type</Th><Th>Schedule</Th><Th>MRP (incl. GST)</Th><Th>In-date stock</Th><Th>PAR (min / max)</Th></tr></thead>
        <tbody>
          {items.isPending && <LoadingRows colSpan={6} />}
          {items.data?.items.length === 0 && <EmptyRow colSpan={6}>No items found.</EmptyRow>}
          {items.data?.items.map((i) => (
            <tr key={i.id} className="hover:bg-slate-50/60">
              <Td>
                <p className="flex items-center gap-1.5 font-medium text-slate-900">{i.name}{i.is_cold_chain && <Snowflake className="h-3.5 w-3.5 text-sky-500" aria-label="Cold chain" />}</p>
                <p className="font-mono text-[11px] text-slate-400">{i.sku}{i.generic_name && ` · ${i.generic_name}`}</p>
              </Td>
              <Td className="capitalize">{i.type === "iol" ? "IOL" : i.type}</Td>
              <Td>{i.schedule === "none" ? <span className="text-xs text-slate-400">OTC</span> : <Badge tone="violet">Sch {i.schedule}</Badge>}</Td>
              <Td>{money(i.mrp)} <span className="text-[11px] text-slate-400">· {Number(i.gst_rate)}% GST</span></Td>
              <Td>
                <p className="font-semibold">{i.on_hand} units</p>
                {i.on_hand !== i.available && <p className="text-[11px] text-slate-400">{i.available} unreserved</p>}
              </Td>
              <Td>{i.par_min} / {i.par_max} {i.below_par && <Badge tone="amber" className="ml-1">Below PAR</Badge>}</Td>
            </tr>
          ))}
        </tbody>
      </Table>
      <Pagination page={page} pageSize={25} total={items.data?.total ?? 0} onPage={setPage} noun="items" />
      {adding && <ItemDialog onClose={() => setAdding(false)} />}
    </>
  );
}

function ItemDialog({ onClose }: { onClose: () => void }) {
  const api = useApi();
  const qc = useQueryClient();
  const toast = useToast();
  const [f, setF] = useState<ItemCreate>({ sku: "", name: "", generic_name: "", type: "drug", schedule: "none",
    dosage_form: "", strength: "", manufacturer: "", hsn_code: "3004", gst_rate: "12", uom: "unit", mrp: "0",
    par_min: 0, par_max: 0, is_cold_chain: false });
  const m = useMutation({
    mutationFn: () => api<Item>("/items", { method: "POST", body: f }),
    onSuccess: (i) => { toast("success", `${i.name} added`); qc.invalidateQueries({ queryKey: ["items"] }); onClose(); },
  });
  const set = (k: keyof ItemCreate) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setF({ ...f, [k]: e.target.value });
  return (
    <Dialog open onClose={onClose} size="lg" title="Add catalogue item"
      footer={<><Button onClick={onClose}>Cancel</Button><Button variant="primary" loading={m.isPending} disabled={!f.sku || f.name.length < 2} onClick={() => m.mutate()}>Add item</Button></>}>
      <div className="space-y-4">
        <ErrorBanner message={m.error ? errorMessage(m.error) : null} />
        <div className="grid gap-4 sm:grid-cols-3">
          <Field label="SKU" required><Input value={f.sku} onChange={set("sku")} /></Field>
          <Field label="Name" required className="sm:col-span-2"><Input value={f.name} onChange={set("name")} /></Field>
          <Field label="Generic name"><Input value={f.generic_name ?? ""} onChange={set("generic_name")} /></Field>
          <Field label="Type"><Select value={f.type} onChange={set("type")}>
            <option value="drug">Drug</option><option value="consumable">Surgical consumable</option><option value="iol">IOL</option><option value="equipment">Equipment</option></Select></Field>
          <Field label="Drug schedule" hint="H/H1/X need a prescription at the counter"><Select value={f.schedule} onChange={set("schedule")}>
            <option value="none">OTC</option><option value="H">Schedule H</option><option value="H1">Schedule H1</option><option value="X">Schedule X</option></Select></Field>
          <Field label="Dosage form"><Input value={f.dosage_form ?? ""} onChange={set("dosage_form")} placeholder="Eye drops" /></Field>
          <Field label="Strength"><Input value={f.strength ?? ""} onChange={set("strength")} /></Field>
          <Field label="Manufacturer"><Input value={f.manufacturer ?? ""} onChange={set("manufacturer")} /></Field>
          <Field label="MRP (₹, incl. GST)" required><Input type="number" step="0.01" value={f.mrp} onChange={set("mrp")} /></Field>
          <Field label="GST %"><Select value={String(f.gst_rate)} onChange={set("gst_rate")}>{["0", "5", "12", "18"].map((g) => <option key={g} value={g}>{g}%</option>)}</Select></Field>
          <Field label="HSN code"><Input value={f.hsn_code ?? ""} onChange={set("hsn_code")} /></Field>
          <Field label="PAR min"><Input type="number" value={f.par_min} onChange={(e) => setF({ ...f, par_min: Number(e.target.value) })} /></Field>
          <Field label="PAR max"><Input type="number" value={f.par_max} onChange={(e) => setF({ ...f, par_max: Number(e.target.value) })} /></Field>
          <label className="flex items-center gap-2 pt-6 text-sm"><input type="checkbox" checked={f.is_cold_chain} onChange={(e) => setF({ ...f, is_cold_chain: e.target.checked })} /> Cold chain (2–8 °C)</label>
        </div>
      </div>
    </Dialog>
  );
}
