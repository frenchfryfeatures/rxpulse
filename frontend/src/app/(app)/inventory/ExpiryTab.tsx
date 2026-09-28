"use client";

import { useQuery } from "@tanstack/react-query";
import { Table, Td, Th } from "@/components/ui/table";
import { useApi } from "@/lib/api/client";
import type { BatchRow, ExpiryBucket, Page } from "@/lib/api/types";
import { money } from "@/lib/format";
import { ExpiryCell } from "./shared";

export function ExpiryTab() {
  const api = useApi();
  const buckets = useQuery({ queryKey: ["expiry-risk"], queryFn: () => api<ExpiryBucket[]>("/stock/expiry-risk") });
  const expired = useQuery({ queryKey: ["batches", "expired-list"], queryFn: () => api<Page<BatchRow>>("/batches", { query: { expiry_status: "expired", sort: "expiry_asc", page_size: 50 } }) });
  const critical = useQuery({ queryKey: ["batches", "critical-list"], queryFn: () => api<Page<BatchRow>>("/batches", { query: { expiry_status: "critical", sort: "expiry_asc", page_size: 50 } }) });
  const tone = (b: string) => (b === "expired" ? "border-rose-200 bg-rose-50" : b === "0-30 days" ? "border-amber-200 bg-amber-50" : "border-slate-200 bg-white");
  const rows = [...(expired.data?.items ?? []), ...(critical.data?.items ?? [])];
  return (
    <div className="space-y-6 p-6">
      <div className="grid gap-3 sm:grid-cols-5">
        {buckets.data?.map((b) => (
          <div key={b.bucket} className={`rounded-xl border p-4 ${tone(b.bucket)}`}>
            <p className="text-xs font-semibold text-slate-600 capitalize">{b.bucket}</p>
            <p className="mt-1 text-xl font-bold">{money(b.value)}</p>
            <p className="text-xs text-slate-500">{b.batches} batches · {b.units} units</p>
          </div>
        ))}
      </div>
      <div>
        <h3 className="mb-2 text-sm font-semibold text-slate-800">Act now: expired and expiring within 30 days</h3>
        <p className="mb-3 text-xs text-slate-500">Expired stock is never allocated. Short-dated stock (&lt; 30 days) is held back from dispensing; move it to a faster-moving location, return it to the vendor, or write it off.</p>
        <div className="overflow-hidden rounded-xl border border-slate-200">
          <Table>
            <thead><tr><Th>Item</Th><Th>Batch</Th><Th>Expiry</Th><Th>Location</Th><Th className="text-right">On hand</Th><Th className="text-right">Value at cost</Th></tr></thead>
            <tbody>
              {rows.map((b) => (
                <tr key={b.balance_id}>
                  <Td><p className="font-medium">{b.item_name}</p><p className="font-mono text-[11px] text-slate-400">{b.sku}</p></Td>
                  <Td className="font-mono text-xs">{b.batch_no}</Td><Td><ExpiryCell row={b} /></Td><Td>{b.location_name}</Td>
                  <Td className="text-right">{b.qty_on_hand}</Td><Td className="text-right font-medium">{money(b.valuation)}</Td>
                </tr>
              ))}
              {rows.length === 0 && <tr><Td colSpan={6} className="py-8 text-center text-slate-400">Nothing at risk. 🎉</Td></tr>}
            </tbody>
          </Table>
        </div>
      </div>
    </div>
  );
}
