"use client";

import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, ArrowRight, ClipboardList, IndianRupee, Package, PackageX, Pill, Timer } from "lucide-react";
import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import { Card, CardHeader, PageHeader } from "@/components/ui/card";
import { useApi } from "@/lib/api/client";
import type { ExpiryBucket, Order, Page } from "@/lib/api/types";
import { useMe } from "@/lib/auth/MeProvider";
import { money, relative } from "@/lib/format";
import { useDashboard } from "@/lib/queries";
import { StatusBadge } from "../pharmacy/status";

function Tile({ label, value, icon, tone = "slate", href }: {
  label: string; value: React.ReactNode; icon: React.ReactNode; tone?: "slate" | "red" | "amber" | "blue";
  href?: string;
}) {
  const ring = { slate: "bg-slate-100 text-slate-600", red: "bg-rose-50 text-rose-600", amber: "bg-amber-50 text-amber-600",
    blue: "bg-blue-50 text-blue-600" }[tone];
  const body = (
    <Card className="flex items-center gap-4 p-5 transition-shadow hover:shadow-sm">
      <span className={`grid h-11 w-11 place-items-center rounded-xl ${ring}`}>{icon}</span>
      <div>
        <p className="text-xs font-medium text-slate-500">{label}</p>
        <p className="text-2xl font-bold text-slate-900">{value}</p>
      </div>
    </Card>
  );
  return href ? <Link href={href}>{body}</Link> : body;
}

export default function DashboardPage() {
  const { me, can, canAny } = useMe();
  const api = useApi();
  const { data: d } = useDashboard();
  const risk = useQuery({
    queryKey: ["expiry-risk"],
    queryFn: () => api<ExpiryBucket[]>("/stock/expiry-risk"),
    enabled: can("inventory:view"),
  });
  const orders = useQuery({
    queryKey: ["pharmacy-orders", "recent"],
    queryFn: () => api<Page<Order>>("/pharmacy/orders", { query: { page_size: 6 } }),
    enabled: canAny("pharmacy_order:view", "requisition:create"),
  });
  const maxValue = Math.max(1, ...(risk.data ?? []).map((b) => Number(b.value)));
  const first = me.user.display_name.split(" ")[0] === "Dr." ? me.user.display_name : me.user.display_name.split(" ")[0];

  return (
    <>
      <PageHeader title={`Good day, ${first}`} subtitle="Here is what needs attention across the pharmacy and stores today." />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {d?.stock_value != null && <Tile label="In-date stock value" value={money(d.stock_value)} icon={<IndianRupee className="h-5 w-5" />} />}
        {d?.active_batches != null && <Tile label="Active batches" value={d.active_batches} icon={<Package className="h-5 w-5" />} href="/inventory" />}
        {d?.expiring_30 != null && <Tile label="Expiring ≤ 30 days" value={d.expiring_30} tone="amber" icon={<Timer className="h-5 w-5" />} href="/inventory?expiry=critical" />}
        {d?.expired_on_hand != null && <Tile label="Expired still on hand" value={d.expired_on_hand} tone="red" icon={<PackageX className="h-5 w-5" />} href="/inventory?expiry=expired" />}
        {d?.below_par_items != null && <Tile label="Items below PAR" value={d.below_par_items} tone="amber" icon={<AlertTriangle className="h-5 w-5" />} href="/inventory?tab=catalog" />}
        {d?.orders_awaiting_dispatch != null && <Tile label="Awaiting dispatch" value={d.orders_awaiting_dispatch} tone="blue" icon={<Pill className="h-5 w-5" />} href="/pharmacy" />}
        {d?.counter_sales_today != null && <Tile label="Counter sales today" value={money(d.counter_sales_today)} icon={<IndianRupee className="h-5 w-5" />} />}
        {d?.requisitions_today != null && <Tile label="Requisitions today" value={d.requisitions_today} icon={<ClipboardList className="h-5 w-5" />} />}
      </div>

      <div className="grid gap-6 xl:grid-cols-5">
        {can("inventory:view") && (
          <Card className="xl:col-span-2">
            <CardHeader title="Expiry risk (value at cost)" actions={<Link href="/inventory?tab=expiry" className="text-xs font-medium text-brand-600">Details</Link>} />
            <div className="space-y-3 p-5">
              {(risk.data ?? []).map((b) => (
                <div key={b.bucket}>
                  <div className="flex justify-between text-xs"><span className="font-medium text-slate-600">{b.bucket}</span>
                    <span className="text-slate-500">{b.batches} batches · {money(b.value)}</span></div>
                  <div className="mt-1 h-2 rounded-full bg-slate-100">
                    <div className={`h-2 rounded-full ${b.bucket === "expired" ? "bg-rose-500" : b.bucket === "0-30 days" ? "bg-amber-500" : "bg-slate-400"}`}
                      style={{ width: `${(Number(b.value) / maxValue) * 100}%` }} />
                  </div>
                </div>
              ))}
            </div>
          </Card>
        )}
        {canAny("pharmacy_order:view", "requisition:create") && (
          <Card className="xl:col-span-3">
            <CardHeader title={can("pharmacy_order:view") ? "Latest pharmacy orders" : "My requisitions"}
              actions={<Link href="/pharmacy" className="flex items-center gap-1 text-xs font-medium text-brand-600">Open pharmacy <ArrowRight className="h-3 w-3" /></Link>} />
            <ul className="divide-y divide-slate-100">
              {orders.data?.items.length === 0 && <li className="px-5 py-8 text-center text-sm text-slate-400">No orders yet.</li>}
              {orders.data?.items.map((o) => (
                <li key={o.id} className="flex items-center justify-between gap-3 px-5 py-3 text-sm">
                  <div className="min-w-0">
                    <p className="font-mono text-xs text-brand-600">{o.order_no}</p>
                    <p className="truncate font-medium text-slate-800">{o.party_name}</p>
                  </div>
                  <div className="flex items-center gap-3">
                    <Badge tone={o.channel === "counter_sale" ? "violet" : "blue"} uppercase={false}>
                      {o.channel === "counter_sale" ? "Counter sale" : "Requisition"}
                    </Badge>
                    <span className="w-24 text-right font-semibold">{money(o.total)}</span>
                    <StatusBadge status={o.status} />
                    <span className="hidden w-20 text-right text-xs text-slate-400 md:block">{relative(o.created_at)}</span>
                  </div>
                </li>
              ))}
            </ul>
          </Card>
        )}
      </div>
    </>
  );
}
