"use client";

import { ChevronsLeft, ChevronsRight, LogOut, Sparkles } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { cn } from "@/components/ui/cn";
import { useAuth } from "@/lib/auth/AuthProvider";
import { useMe } from "@/lib/auth/MeProvider";
import { NAV } from "@/lib/nav";
import { useDashboard } from "@/lib/queries";

export function Sidebar() {
  const pathname = usePathname();
  const { canAny, me, primaryRole } = useMe();
  const { logout } = useAuth();
  const dash = useDashboard();
  const [collapsed, setCollapsed] = useState(false);
  const items = NAV.filter((n) => canAny(...n.anyOf));
  const initials = me.user.display_name.replace(/^Dr\.?\s*/, "").split(/\s+/).map((p) => p[0]).slice(0, 2).join("");

  return (
    <aside className={cn("no-print sticky top-0 flex h-screen shrink-0 flex-col border-r border-slate-200 bg-white",
      collapsed ? "w-[72px]" : "w-64")}>
      <div className="flex items-center justify-between gap-2 border-b border-slate-100 px-4 py-4">
        <Link href="/dashboard" className="flex items-center gap-3">
          <span className="grid h-9 w-9 place-items-center rounded-lg bg-ink text-sm font-bold text-white">Rx</span>
          {!collapsed && (
            <span className="leading-tight">
              <span className="block text-[15px] font-bold text-slate-900">RxPulse <span className="text-brand-600">IQ</span></span>
              <span className="block text-[10px] font-semibold tracking-wider text-slate-400 uppercase">Eye Care Hospital</span>
            </span>
          )}
        </Link>
        <button onClick={() => setCollapsed((c) => !c)} className="rounded p-1 text-slate-400 hover:bg-slate-100"
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}>
          {collapsed ? <ChevronsRight className="h-4 w-4" /> : <ChevronsLeft className="h-4 w-4" />}
        </button>
      </div>

      <nav className="flex-1 space-y-1 overflow-y-auto px-3 py-4" aria-label="Main">
        {items.map((n) => {
          const active = pathname === n.href || pathname.startsWith(`${n.href}/`);
          const Icon = n.icon;
          return (
            <Link key={n.href} href={n.href} title={collapsed ? n.label : undefined}
              className={cn(
                "flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-colors",
                active ? "border-2 border-ink bg-white text-slate-900" : "border-2 border-transparent text-slate-600 hover:bg-slate-50",
              )}>
              <Icon className="h-[18px] w-[18px] shrink-0 text-slate-500" />
              {!collapsed && <span className="flex-1">{n.label}</span>}
              {!collapsed && n.badge === "batches" && dash.data?.active_batches != null && (
                <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-semibold text-slate-600">
                  {dash.data.active_batches}
                </span>
              )}
              {!collapsed && n.badge === "agent" && (
                <span className="rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 text-[10px] font-semibold text-slate-600">
                  Agent
                </span>
              )}
            </Link>
          );
        })}
      </nav>

      {!collapsed && canAny("ai:chat") && (
        <div className="mx-3 mb-3 rounded-2xl bg-ink p-4 text-white">
          <div className="flex items-center gap-2 text-sm font-semibold">
            <Sparkles className="h-4 w-4 text-blue-300" /> RxPulse Copilot
            <span className="rounded bg-blue-500/20 px-1.5 py-0.5 text-[10px] text-blue-200">Preview</span>
          </div>
          <p className="mt-1 text-xs text-slate-300">Ask about stock, expiries and requisitions. Arrives with the agents phase.</p>
          <Link href="/ai-studio" className="mt-3 block rounded-lg bg-brand-600 py-2 text-center text-xs font-semibold hover:bg-brand-700">
            Open AI Studio
          </Link>
        </div>
      )}

      <div className="flex items-center gap-3 border-t border-slate-100 px-4 py-3">
        <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-ink text-xs font-bold text-white">{initials}</span>
        {!collapsed && (
          <div className="min-w-0 flex-1 leading-tight">
            <p className="truncate text-sm font-semibold text-slate-900">{me.user.display_name}</p>
            <p className="flex items-center gap-1 truncate text-[11px] text-slate-500">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />{primaryRole}
            </p>
          </div>
        )}
        <button onClick={() => logout()} className="rounded p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
          aria-label="Sign out" title="Sign out">
          <LogOut className="h-4 w-4" />
        </button>
      </div>
    </aside>
  );
}
