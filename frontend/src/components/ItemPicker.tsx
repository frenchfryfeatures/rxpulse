"use client";

import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useApi } from "@/lib/api/client";
import type { Item, Page } from "@/lib/api/types";

/** Type-ahead item search against the catalogue. */
export function ItemPicker({ onPick, dispensable, placeholder = "Search medicine or consumable…", exclude = [] }: {
  onPick: (item: Item) => void; dispensable?: boolean; placeholder?: string; exclude?: string[];
}) {
  const api = useApi();
  const [q, setQ] = useState("");
  const [debounced, setDebounced] = useState("");
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(q), 200);
    return () => clearTimeout(t);
  }, [q]);
  useEffect(() => {
    const close = (e: MouseEvent) => { if (!box.current?.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);
  const items = useQuery({
    queryKey: ["items-search", debounced, dispensable],
    queryFn: () => api<Page<Item>>("/items", { query: { q: debounced, dispensable, page_size: 12 } }),
    enabled: open,
  });
  const results = (items.data?.items ?? []).filter((i) => !exclude.includes(i.id));
  return (
    <div ref={box} className="relative">
      <Search className="pointer-events-none absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2 text-slate-400" />
      <input value={q} placeholder={placeholder} onFocus={() => setOpen(true)}
        onChange={(e) => { setQ(e.target.value); setOpen(true); }}
        className="w-full rounded-lg border border-slate-200 py-2 pr-3 pl-9 text-sm focus:border-brand-500 focus:ring-2 focus:ring-brand-100 focus:outline-none" />
      {open && (
        <ul className="absolute z-10 mt-1 max-h-72 w-full overflow-y-auto rounded-xl border border-slate-200 bg-white p-1 shadow-lg">
          {items.isPending && <li className="px-3 py-2 text-xs text-slate-400">Searching…</li>}
          {!items.isPending && results.length === 0 && <li className="px-3 py-2 text-xs text-slate-400">No matching items</li>}
          {results.map((i) => (
            <li key={i.id}>
              <button type="button" onClick={() => { onPick(i); setQ(""); setOpen(false); }}
                className="flex w-full items-center justify-between gap-3 rounded-lg px-3 py-2 text-left hover:bg-slate-50">
                <span className="min-w-0">
                  <span className="block truncate text-sm font-medium text-slate-800">{i.name}</span>
                  <span className="font-mono text-[11px] text-slate-400">{i.sku}{i.schedule !== "none" && ` · Schedule ${i.schedule}`}</span>
                </span>
                <span className="shrink-0 text-right text-xs">
                  <span className={i.available > 0 ? "text-emerald-600" : "text-rose-500"}>{i.available} avail.</span>
                  <span className="block text-slate-400">₹{Number(i.mrp).toFixed(2)}</span>
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
