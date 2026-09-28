"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { ClipboardList, Download, FileText, Plus, Printer, RotateCcw, Truck, XCircle } from "lucide-react";
import { useState } from "react";
import { Guard } from "@/components/auth/Guard";
import { Badge, Chip } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, PageHeader } from "@/components/ui/card";
import { Tabs } from "@/components/ui/tabs";
import { EmptyRow, FilterSelect, LoadingRows, Pagination, SearchInput, Table, Td, Th, Toolbar } from "@/components/ui/table";
import { useApi } from "@/lib/api/client";
import type { Order, OrderStatus, Page } from "@/lib/api/types";
import { useMe } from "@/lib/auth/MeProvider";
import { dateShort, downloadCsv, money } from "@/lib/format";
import { CancelDialog, DispatchDialog, OrderDetailDialog, PickListDialog, ReturnDialog } from "./OrderDialogs";
import { NewOrderDialog } from "./NewOrderDialog";
import { StatusBadge } from "./status";

type Channel = "all" | "counter_sale" | "requisition";
type Sort = "date_desc" | "date_asc" | "total_desc" | "total_asc";
type Action = "detail" | "pick" | "dispatch" | "return" | "cancel";

export default function PharmacyPage() {
  return (
    <Guard anyOf={["pharmacy_order:view", "pharmacy_order:create", "requisition:create"]}>
      <Pharmacy />
    </Guard>
  );
}

function Pharmacy() {
  const api = useApi();
  const { can, me } = useMe();
  const staff = can("pharmacy_order:view") || can("pharmacy_order:create");
  const [channel, setChannel] = useState<Channel>(staff ? "all" : "requisition");
  const [status, setStatus] = useState<"all" | OrderStatus>("all");
  const [sort, setSort] = useState<Sort>("date_desc");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [creating, setCreating] = useState<"counter_sale" | "requisition" | null>(null);
  const [action, setAction] = useState<{ kind: Action; order: Order } | null>(null);

  const query = { channel: channel === "all" ? undefined : channel, status: status === "all" ? undefined : status, q, sort };
  const orders = useQuery({
    queryKey: ["pharmacy-orders", query, page, pageSize],
    queryFn: () => api<Page<Order>>("/pharmacy/orders", { query: { ...query, page, page_size: pageSize } }),
    placeholderData: keepPreviousData,
  });
  const reset = () => setPage(1);

  const exportCsv = async () => {
    const all = await api<Page<Order>>("/pharmacy/orders", { query: { ...query, page: 1, page_size: 100 } });
    downloadCsv("pharmacy-orders.csv", [
      ["Order", "Channel", "Party", "Date", "Status", "Total", "GST", "Invoice", "Prescription"],
      ...all.items.map((o) => [o.order_no, o.channel, o.party_name, o.created_at, o.status, o.total, o.gst_amount, o.invoice_no, o.prescription_ref]),
    ]);
  };

  return (
    <>
      <PageHeader
        title={staff ? "Pharmacy Orders & FEFO Dispatch" : "Pharmacy Requisitions"}
        subtitle={staff
          ? "Counter sales to patients and walk-in buyers, doctor & OT requisitions, automated FEFO allocation, pick lists and dispatch"
          : "Request medicines and consumables from the hospital pharmacy for your patients, OT list or ward"}
        actions={<>
          {staff && <Button icon={<Download className="h-4 w-4" />} onClick={exportCsv}>Export</Button>}
          {(can("requisition:create") || can("pharmacy_order:create")) && (
            <Button variant={can("pharmacy_order:create") ? "secondary" : "primary"} icon={<ClipboardList className="h-4 w-4" />} onClick={() => setCreating("requisition")}>New Requisition</Button>)}
          {can("pharmacy_order:create") && <Button variant="primary" icon={<Plus className="h-4 w-4" />} onClick={() => setCreating("counter_sale")}>New Counter Sale</Button>}
        </>}
      />

      {staff && (
        <Tabs<Channel> value={channel} onChange={(v) => { setChannel(v); reset(); }} tabs={[
          { value: "all", label: "All Orders" }, { value: "counter_sale", label: "Counter Sales" },
          { value: "requisition", label: "Doctor & OT Requisitions" }]} />
      )}

      <Card className="overflow-hidden">
        <Toolbar shown={orders.data?.items.length} total={orders.data?.total} onRefresh={() => orders.refetch()} refreshing={orders.isFetching}>
          <SearchInput value={q} onChange={(v) => { setQ(v); reset(); }} placeholder="Search order #, patient, MRN, doctor, invoice #…" />
          <FilterSelect value={status} onChange={(v) => { setStatus(v); reset(); }} options={[
            { value: "all", label: "All statuses" }, { value: "allocated", label: "Awaiting dispatch" },
            { value: "dispatched", label: "Dispatched" }, { value: "partially_returned", label: "Part returned" },
            { value: "returned", label: "Returned" }, { value: "cancelled", label: "Cancelled" }]} />
          <FilterSelect<Sort> icon="sort" value={sort} onChange={setSort} options={[
            { value: "date_desc", label: "Sort: Date (newest first)" }, { value: "date_asc", label: "Sort: Date (oldest first)" },
            { value: "total_desc", label: "Sort: Total (high → low)" }, { value: "total_asc", label: "Sort: Total (low → high)" }]} />
        </Toolbar>
        <Table>
          <thead><tr>
            <Th>Order number</Th><Th>Patient / requested by</Th><Th>Date</Th><Th>FEFO batches allocated</Th>
            <Th>Order total</Th><Th>Invoice #</Th><Th>Status</Th><Th className="text-right">Actions</Th>
          </tr></thead>
          <tbody>
            {orders.isPending && <LoadingRows colSpan={8} />}
            {orders.data?.items.length === 0 && <EmptyRow colSpan={8}>No pharmacy orders match your filters.</EmptyRow>}
            {orders.data?.items.map((o) => {
              const loc = o.location_id;
              const ownReq = o.channel === "requisition" && o.requested_by_id === me.user.id;
              return (
                <tr key={o.id} className="hover:bg-slate-50/60">
                  <Td>
                    <button onClick={() => setAction({ kind: "detail", order: o })} className="font-mono text-xs text-brand-600 hover:underline">{o.order_no}</button>
                    <div className="mt-1">
                      <Badge tone={o.channel === "counter_sale" ? "violet" : "blue"} uppercase={false}>{o.channel === "counter_sale" ? "Counter sale" : "Requisition"}</Badge>
                    </div>
                  </Td>
                  <Td>
                    <p className="font-medium text-slate-900">{o.party_name}</p>
                    <p className="text-[11px] text-slate-400">
                      {o.channel === "counter_sale"
                        ? (o.prescription_ref ? `Rx ${o.prescription_ref}${o.prescriber_name ? ` · ${o.prescriber_name}` : ""}` : "OTC, no prescription")
                        : (o.surgery_ref ?? `Raised by ${o.created_by_name}`)}
                    </p>
                  </Td>
                  <Td className="text-slate-600">{dateShort(o.created_at)}</Td>
                  <Td>
                    <div className="flex max-w-xs flex-wrap gap-1">
                      {o.lines.flatMap((l) => l.allocations.map((a) => (
                        <Chip key={l.id + a.batch_id}>{a.batch_no}: {a.qty}u</Chip>
                      )))}
                    </div>
                  </Td>
                  <Td className="font-semibold">{money(o.total)}</Td>
                  <Td>{o.invoice_no
                    ? <span className="flex items-center gap-1 font-mono text-xs text-brand-600"><FileText className="h-3.5 w-3.5" />{o.invoice_no}</span>
                    : <span className="text-xs text-slate-400">{o.channel === "requisition" ? "Internal" : "On dispatch"}</span>}</Td>
                  <Td><StatusBadge status={o.status} /></Td>
                  <Td>
                    <div className="flex justify-end gap-2">
                      <Button size="sm" icon={<Printer className="h-3.5 w-3.5" />} onClick={() => setAction({ kind: "pick", order: o })}>Pick List</Button>
                      {o.status === "allocated" && can("pharmacy_order:dispatch", loc) && (
                        <Button size="sm" variant="primary" icon={<Truck className="h-3.5 w-3.5" />} onClick={() => setAction({ kind: "dispatch", order: o })}>Dispatch</Button>)}
                      {o.status === "allocated" && (can("pharmacy_order:create", loc) || ownReq) && (
                        <Button size="sm" variant="outline-danger" icon={<XCircle className="h-3.5 w-3.5" />} onClick={() => setAction({ kind: "cancel", order: o })}>Cancel</Button>)}
                      {(o.status === "dispatched" || o.status === "partially_returned") && can("pharmacy_order:return", loc) && (
                        <Button size="sm" variant="outline-brand" icon={<RotateCcw className="h-3.5 w-3.5" />} onClick={() => setAction({ kind: "return", order: o })}>Return</Button>)}
                    </div>
                  </Td>
                </tr>
              );
            })}
          </tbody>
        </Table>
        <Pagination page={page} pageSize={pageSize} total={orders.data?.total ?? 0} onPage={setPage}
          onPageSize={(n) => { setPageSize(n); reset(); }} noun="orders" />
      </Card>

      {creating && <NewOrderDialog channel={creating} onClose={() => setCreating(null)} />}
      {action?.kind === "detail" && <OrderDetailDialog order={action.order} onClose={() => setAction(null)} />}
      {action?.kind === "pick" && <PickListDialog order={action.order} onClose={() => setAction(null)} />}
      {action?.kind === "dispatch" && <DispatchDialog order={action.order} onClose={() => setAction(null)} />}
      {action?.kind === "cancel" && <CancelDialog order={action.order} onClose={() => setAction(null)} />}
      {action?.kind === "return" && <ReturnDialog order={action.order} onClose={() => setAction(null)} />}
    </>
  );
}
