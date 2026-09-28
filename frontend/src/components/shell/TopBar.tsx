"use client";

import { AlertTriangle, Bell, Building2, ChevronDown, Search } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { useMe } from "@/lib/auth/MeProvider";
import { config } from "@/lib/config";
import { useDashboard } from "@/lib/queries";

export function TopBar() {
  const { me, primaryRole, can } = useMe();
  const dash = useDashboard();
  const router = useRouter();
  const [q, setQ] = useState("");
  const [openAlerts, setOpenAlerts] = useState(false);
  const search = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        search.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const d = dash.data;
  const alerts = [
    d?.expired_on_hand ? { n: d.expired_on_hand, label: "expired batch(es) still on hand", href: "/inventory?expiry=expired" } : null,
    d?.expiring_30 ? { n: d.expiring_30, label: "batch(es) expiring within 30 days", href: "/inventory?expiry=critical" } : null,
    d?.below_par_items ? { n: d.below_par_items, label: "item(s) below PAR level", href: "/inventory?tab=catalog" } : null,
    d?.orders_awaiting_dispatch ? { n: d.orders_awaiting_dispatch, label: "pharmacy order(s) awaiting dispatch", href: "/pharmacy" } : null,
  ].filter(Boolean) as { n: number; label: string; href: string }[];

  const scope = me.user.roles.find((r) => r.location_name)?.location_name ?? "All locations";

  return (
    <header className="no-print sticky top-0 z-30 flex items-center gap-4 border-b border-slate-200 bg-white/95 px-6 py-3 backdrop-blur">
      <div className="hidden items-center gap-2 text-sm md:flex">
        <span className="font-semibold text-slate-900">{config.hospitalName}</span>
        <span className="text-slate-300">•</span>
        <span className="flex items-center gap-1 text-slate-500"><Building2 className="h-3.5 w-3.5" />{scope}</span>
      </div>

      {can("inventory:view") ? (
        <form className="relative mx-auto w-full max-w-lg" onSubmit={(e) => {
          e.preventDefault();
          if (q.trim()) router.push(`/inventory?q=${encodeURIComponent(q.trim())}`);
        }}>
          <Search className="pointer-events-none absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2 text-slate-400" />
          <input ref={search} value={q} onChange={(e) => setQ(e.target.value)}
            placeholder="Search medicines, batches, SKUs, bins…"
            className="w-full rounded-xl border border-slate-200 bg-slate-50 py-2 pr-16 pl-9 text-sm focus:border-brand-500 focus:bg-white focus:outline-none" />
          <kbd className="absolute top-1/2 right-3 -translate-y-1/2 rounded border border-slate-200 bg-white px-1.5 text-[10px] text-slate-400">Ctrl K</kbd>
        </form>
      ) : <div className="flex-1" />}

      <div className="relative">
        <button onClick={() => setOpenAlerts((o) => !o)} className="relative rounded-xl border border-slate-200 p-2 text-slate-500 hover:bg-slate-50"
          aria-label={`${alerts.length} alerts`}>
          <Bell className="h-4 w-4" />
          {alerts.length > 0 && (
            <span className="absolute -top-1.5 -right-1.5 grid h-5 min-w-5 place-items-center rounded-full bg-rose-600 px-1 text-[10px] font-bold text-white">
              {alerts.reduce((s, a) => s + a.n, 0)}
            </span>
          )}
        </button>
        {openAlerts && (
          <div className="absolute right-0 mt-2 w-80 rounded-xl border border-slate-200 bg-white p-2 shadow-lg">
            <p className="px-2 py-1.5 text-xs font-semibold tracking-wider text-slate-400 uppercase">Alerts</p>
            {alerts.length === 0 && <p className="px-2 py-3 text-sm text-slate-500">You&apos;re all caught up.</p>}
            {alerts.map((a) => (
              <Link key={a.href + a.label} href={a.href} onClick={() => setOpenAlerts(false)}
                className="flex items-start gap-2 rounded-lg px-2 py-2 text-sm hover:bg-slate-50">
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-500" />
                <span><b>{a.n}</b> {a.label}</span>
              </Link>
            ))}
          </div>
        )}
      </div>

      <div className="flex items-center gap-2 border-l border-slate-200 pl-4">
        <div className="text-right leading-tight">
          <p className="text-sm font-semibold text-slate-900">{me.user.display_name}</p>
          <p className="text-[10px] font-semibold tracking-wider text-brand-600 uppercase">{primaryRole}</p>
        </div>
        <ChevronDown className="h-4 w-4 text-slate-400" />
      </div>
    </header>
  );
}
