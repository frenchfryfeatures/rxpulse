"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { EmptyRow, FilterSelect, LoadingRows, Pagination, Table, Td, Th, Toolbar } from "@/components/ui/table";
import { useApi } from "@/lib/api/client";
import type { Ledger, Page } from "@/lib/api/types";
import { dateTime } from "@/lib/format";

const LABEL: Record<string, string> = {
  receipt: "Receipt", adjustment: "Adjustment", transfer_out: "Transfer out", transfer_in: "Transfer in",
  issue: "Dispatched", return_in: "Returned", writeoff: "Write-off",
};

export function MovementsTab() {
  const api = useApi();
  const [reason, setReason] = useState("all");
  const [page, setPage] = useState(1);
  const moves = useQuery({
    queryKey: ["movements", reason, page],
    queryFn: () => api<Page<Ledger>>("/stock/movements", { query: { reason: reason === "all" ? undefined : reason, page, page_size: 25 } }),
    placeholderData: keepPreviousData,
  });
  return (
    <>
      <Toolbar shown={moves.data?.items.length} total={moves.data?.total} onRefresh={() => moves.refetch()} refreshing={moves.isFetching}>
        <FilterSelect value={reason} onChange={(v) => { setReason(v); setPage(1); }}
          options={[{ value: "all", label: "All movements" }, ...Object.entries(LABEL).map(([value, label]) => ({ value, label }))]} />
      </Toolbar>
      <Table>
        <thead><tr><Th>When</Th><Th>Movement</Th><Th>Item / batch</Th><Th>Location</Th><Th className="text-right">Qty</Th><Th>By</Th><Th>Note</Th></tr></thead>
        <tbody>
          {moves.isPending && <LoadingRows colSpan={7} />}
          {moves.data?.items.length === 0 && <EmptyRow colSpan={7}>No movements.</EmptyRow>}
          {moves.data?.items.map((l) => (
            <tr key={l.id}>
              <Td className="text-xs whitespace-nowrap">{dateTime(l.created_at)}</Td>
              <Td><Badge tone={l.qty_delta > 0 ? "green" : l.reason === "writeoff" ? "red" : "slate"} uppercase={false}>{LABEL[l.reason] ?? l.reason}</Badge></Td>
              <Td><p className="font-medium">{l.item_name}</p><p className="font-mono text-[11px] text-slate-400">{l.batch_no}</p></Td>
              <Td className="text-xs">{l.location_name}</Td>
              <Td className={`text-right font-mono ${l.qty_delta > 0 ? "text-emerald-600" : "text-rose-600"}`}>{l.qty_delta > 0 ? "+" : ""}{l.qty_delta}</Td>
              <Td className="text-xs">{l.actor_name ?? "System"}</Td>
              <Td className="max-w-xs truncate text-xs text-slate-500">{l.note}</Td>
            </tr>
          ))}
        </tbody>
      </Table>
      <Pagination page={page} pageSize={25} total={moves.data?.total ?? 0} onPage={setPage} noun="movements" />
    </>
  );
}
