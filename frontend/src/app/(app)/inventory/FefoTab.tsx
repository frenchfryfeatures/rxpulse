"use client";

import { useMutation } from "@tanstack/react-query";
import { Zap } from "lucide-react";
import { useState } from "react";
import { ItemPicker } from "@/components/ItemPicker";
import { Button } from "@/components/ui/button";
import { ErrorBanner, Field, Input, Select } from "@/components/ui/form";
import { Table, Td, Th } from "@/components/ui/table";
import { errorMessage, useApi } from "@/lib/api/client";
import type { FefoPreview, Item } from "@/lib/api/types";
import { dateOnly } from "@/lib/format";
import { useScopedLocations } from "./shared";

export function FefoTab() {
  const api = useApi();
  const locations = useScopedLocations("inventory:view");
  const [item, setItem] = useState<Item | null>(null);
  const [location, setLocation] = useState(locations.find((l) => l.type === "pharmacy")?.id ?? locations[0]?.id ?? "");
  const [qty, setQty] = useState(10);
  const preview = useMutation({
    mutationFn: () => api<FefoPreview>("/stock/fefo/preview", { method: "POST", body: { item_id: item!.id, location_id: location, qty } }),
  });
  return (
    <div className="grid gap-6 p-6 lg:grid-cols-[360px_1fr]">
      <div className="space-y-4">
        <p className="text-sm text-slate-600">
          Preview how an order would be allocated: <b>first-expiry, first-out</b>, skipping expired batches and any batch
          with less than the minimum remaining shelf life (30 days by default).
        </p>
        <Field label="Item">{item ? (
          <div className="flex items-center justify-between rounded-lg border border-slate-200 px-3 py-2 text-sm"><b>{item.name}</b>
            <Button size="sm" variant="ghost" onClick={() => { setItem(null); preview.reset(); }}>Change</Button></div>
        ) : <ItemPicker onPick={setItem} />}</Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Location"><Select value={location} onChange={(e) => setLocation(e.target.value)}>{locations.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}</Select></Field>
          <Field label="Quantity"><Input type="number" min={1} value={qty} onChange={(e) => setQty(Number(e.target.value))} /></Field>
        </div>
        <Button variant="primary" icon={<Zap className="h-4 w-4" />} disabled={!item || qty < 1} loading={preview.isPending} onClick={() => preview.mutate()}>Run FEFO allocation</Button>
      </div>
      <div>
        <ErrorBanner message={preview.error ? errorMessage(preview.error) : null} />
        {preview.data && (
          <div className="space-y-3">
            <div className="flex gap-3 text-sm">
              <span className="rounded-lg bg-slate-100 px-3 py-1.5">Requested <b>{preview.data.requested}</b></span>
              <span className="rounded-lg bg-emerald-50 px-3 py-1.5 text-emerald-700">Allocatable <b>{preview.data.allocatable}</b></span>
              {preview.data.shortfall > 0 && <span className="rounded-lg bg-rose-50 px-3 py-1.5 text-rose-700">Shortfall <b>{preview.data.shortfall}</b></span>}
            </div>
            <div className="overflow-hidden rounded-xl border border-slate-200">
              <Table className="min-w-0">
                <thead><tr><Th>Pick order</Th><Th>Batch</Th><Th>Expiry</Th><Th>Bin</Th><Th className="text-right">Qty</Th></tr></thead>
                <tbody>
                  {preview.data.picks.map((p, i) => (
                    <tr key={p.batch_id}><Td>#{i + 1}</Td><Td className="font-mono text-xs">{p.batch_no}</Td><Td>{dateOnly(p.expiry_date)}</Td>
                      <Td className="font-mono text-xs">{p.bin_code ?? "—"}</Td><Td className="text-right font-semibold">{p.qty}</Td></tr>
                  ))}
                  {preview.data.picks.length === 0 && <tr><Td colSpan={5} className="py-8 text-center text-slate-400">No in-date stock available at this location.</Td></tr>}
                </tbody>
              </Table>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
