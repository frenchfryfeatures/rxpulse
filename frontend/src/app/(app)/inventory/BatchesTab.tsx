"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { ArrowLeftRight, CalendarDays, Download, Eye, PackagePlus, SlidersHorizontal } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { EmptyRow, FilterSelect, LoadingRows, Pagination, SearchInput, Table, Td, Th, Toolbar } from "@/components/ui/table";
import { useApi } from "@/lib/api/client";
import type { BatchRow, Page } from "@/lib/api/types";
import { useMe } from "@/lib/auth/MeProvider";
import { dateShort, downloadCsv, money, time } from "@/lib/format";
import { AdjustDialog, LedgerDialog, ReceiveDialog, TransferDialog } from "./StockDialogs";
import { ExpiryCell, StockStatus, useScopedLocations } from "./shared";

type Sort = "received_desc" | "received_asc" | "expiry_asc" | "expiry_desc" | "name_asc" | "qty_desc";
type Expiry = "all" | "expired" | "critical" | "warning" | "ok";

export function BatchesTab({ initialQ, initialExpiry }: { initialQ: string; initialExpiry: string }) {
  const api = useApi();
  const { can } = useMe();
  const locations = useScopedLocations("inventory:view");
  const [q, setQ] = useState(initialQ);
  const [expiry, setExpiry] = useState<Expiry>(initialExpiry as Expiry);
  const [location, setLocation] = useState("all");
  const [sort, setSort] = useState<Sort>("received_desc");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);
  const [dialog, setDialog] = useState<{ kind: "view" | "adjust" | "transfer"; row: BatchRow } | { kind: "receive" } | null>(null);

  const query = { q, expiry_status: expiry === "all" ? undefined : expiry, location_id: location === "all" ? undefined : location, sort };
  const batches = useQuery({
    queryKey: ["batches", query, page, pageSize],
    queryFn: () => api<Page<BatchRow>>("/batches", { query: { ...query, page, page_size: pageSize } }),
    placeholderData: keepPreviousData,
  });
  const reset = () => setPage(1);

  const exportCsv = async () => {
    const all = await api<Page<BatchRow>>("/batches", { query: { ...query, page: 1, page_size: 100 } });
    downloadCsv("batches.csv", [
      ["Item", "SKU", "Batch", "Expiry", "Status", "On hand", "Reserved", "Location", "Bin", "Unit cost", "Valuation"],
      ...all.items.map((b) => [b.item_name, b.sku, b.batch_no, b.expiry_date, b.expiry_status, b.qty_on_hand,
        b.qty_reserved, b.location_name, b.bin_code, b.unit_cost, b.valuation]),
    ]);
  };

  return (
    <>
      <Toolbar shown={batches.data?.items.length} total={batches.data?.total} onRefresh={() => batches.refetch()} refreshing={batches.isFetching}>
        <SearchInput value={q} onChange={(v) => { setQ(v); reset(); }} placeholder="Search medicine, SKU, batch #, bin…" />
        <FilterSelect<Expiry> value={expiry} onChange={(v) => { setExpiry(v); reset(); }} options={[
          { value: "all", label: "All batches" }, { value: "expired", label: "Expired" },
          { value: "critical", label: "Expiring ≤ 30 days" }, { value: "warning", label: "Expiring 31–90 days" },
          { value: "ok", label: "> 90 days" }]} />
        {locations.length > 1 && (
          <FilterSelect value={location} onChange={(v) => { setLocation(v); reset(); }}
            options={[{ value: "all", label: "All locations" }, ...locations.map((l) => ({ value: l.id, label: l.name }))]} />
        )}
        <FilterSelect<Sort> icon="sort" value={sort} onChange={setSort} options={[
          { value: "received_desc", label: "Sort: Inward date (newest)" }, { value: "received_asc", label: "Sort: Inward date (oldest)" },
          { value: "expiry_asc", label: "Sort: Expiry (soonest)" }, { value: "expiry_desc", label: "Sort: Expiry (latest)" },
          { value: "name_asc", label: "Sort: Name (A–Z)" }, { value: "qty_desc", label: "Sort: Quantity (high)" }]} />
        <Button size="sm" icon={<Download className="h-3.5 w-3.5" />} onClick={exportCsv}>Export</Button>
        {can("grn:create") && <Button size="sm" variant="primary" icon={<PackagePlus className="h-3.5 w-3.5" />} onClick={() => setDialog({ kind: "receive" })}>Receive stock</Button>}
      </Toolbar>
      <Table>
        <thead><tr>
          <Th>Medicine & SKU</Th><Th>Batch number</Th><Th>Inward date</Th><Th>Expiry date</Th><Th>Status</Th>
          <Th>Available stock</Th><Th>Location</Th><Th>Valuation</Th><Th className="text-right">Actions</Th>
        </tr></thead>
        <tbody>
          {batches.isPending && <LoadingRows colSpan={9} />}
          {batches.data?.items.length === 0 && <EmptyRow colSpan={9}>No batches match your filters.</EmptyRow>}
          {batches.data?.items.map((b) => (
            <tr key={b.balance_id} className="hover:bg-slate-50/60">
              <Td>
                <p className="font-medium text-slate-900">{b.item_name}</p>
                <p className="font-mono text-[11px] text-slate-400">{b.sku}{b.schedule !== "none" && <span className="ml-1 text-violet-500">Sch {b.schedule}</span>}</p>
              </Td>
              <Td className="font-mono text-xs">{b.batch_no}</Td>
              <Td>
                <p className="flex items-center gap-1.5 text-slate-800"><CalendarDays className="h-3.5 w-3.5 text-brand-500" />{dateShort(b.received_at)}</p>
                <p className="pl-5 font-mono text-[11px] text-slate-400">{time(b.received_at)}</p>
              </Td>
              <Td><ExpiryCell row={b} /></Td>
              <Td><StockStatus row={b} /></Td>
              <Td>
                <p className="font-semibold text-slate-900">{b.qty_available} units</p>
                {b.qty_reserved > 0 && <p className="text-[11px] text-slate-400">{b.qty_on_hand} on hand · {b.qty_reserved} reserved</p>}
              </Td>
              <Td>
                <p className="text-slate-700">{b.location_name}</p>
                {b.bin_code && <p className="font-mono text-[11px] text-slate-400">Bin {b.bin_code}</p>}
              </Td>
              <Td className="font-medium">{money(b.valuation)}</Td>
              <Td>
                <div className="flex justify-end gap-2">
                  <Button size="sm" variant="outline-brand" icon={<Eye className="h-3.5 w-3.5" />} onClick={() => setDialog({ kind: "view", row: b })}>View</Button>
                  {can("inventory:adjust", b.location_id) && (
                    <Button size="sm" variant="outline-warn" icon={<SlidersHorizontal className="h-3.5 w-3.5" />} onClick={() => setDialog({ kind: "adjust", row: b })}>Adjust</Button>)}
                  {can("inventory:transfer", b.location_id) && b.expiry_status !== "expired" && (
                    <Button size="sm" variant="secondary" icon={<ArrowLeftRight className="h-3.5 w-3.5" />} onClick={() => setDialog({ kind: "transfer", row: b })}>Transfer</Button>)}
                </div>
              </Td>
            </tr>
          ))}
        </tbody>
      </Table>
      <Pagination page={page} pageSize={pageSize} total={batches.data?.total ?? 0} onPage={setPage}
        onPageSize={(n) => { setPageSize(n); reset(); }} noun="batches" />

      {dialog?.kind === "receive" && <ReceiveDialog onClose={() => setDialog(null)} />}
      {dialog?.kind === "view" && <LedgerDialog row={dialog.row} onClose={() => setDialog(null)} />}
      {dialog?.kind === "adjust" && <AdjustDialog row={dialog.row} onClose={() => setDialog(null)} />}
      {dialog?.kind === "transfer" && <TransferDialog row={dialog.row} onClose={() => setDialog(null)} />}
    </>
  );
}
