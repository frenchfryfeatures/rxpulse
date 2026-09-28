import { ChevronLeft, ChevronRight, Filter, RefreshCw, Search } from "lucide-react";
import { Button } from "./button";
import { cn } from "./cn";

export function Table({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <div className="overflow-x-auto">
      <table className={cn("w-full min-w-[720px] text-left text-sm", className)}>{children}</table>
    </div>
  );
}

export function Th({ children, className }: { children?: React.ReactNode; className?: string }) {
  return (
    <th className={cn("bg-slate-50/70 px-4 py-3 text-[11px] font-semibold tracking-wider text-slate-500 uppercase",
      className)}>
      {children}
    </th>
  );
}

export function Td({ children, className, colSpan }: { children?: React.ReactNode; className?: string;
  colSpan?: number }) {
  return <td colSpan={colSpan} className={cn("border-t border-slate-100 px-4 py-3.5 align-middle", className)}>{children}</td>;
}

export function EmptyRow({ colSpan, children }: { colSpan: number; children: React.ReactNode }) {
  return (
    <tr>
      <Td colSpan={colSpan} className="py-12 text-center text-sm text-slate-400">{children}</Td>
    </tr>
  );
}

export function LoadingRows({ colSpan, rows = 5 }: { colSpan: number; rows?: number }) {
  return (
    <>
      {Array.from({ length: rows }).map((_, i) => (
        <tr key={i}>
          <Td colSpan={colSpan}><div className="h-4 animate-pulse rounded bg-slate-100" /></Td>
        </tr>
      ))}
    </>
  );
}

export function SearchInput({ value, onChange, placeholder }: {
  value: string; onChange: (v: string) => void; placeholder: string;
}) {
  return (
    <div className="relative w-full max-w-md">
      <Search className="pointer-events-none absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2 text-slate-400" />
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-full rounded-lg border border-slate-200 bg-white py-2 pr-3 pl-9 text-sm placeholder:text-slate-400
          focus:border-brand-500 focus:ring-2 focus:ring-brand-100 focus:outline-none"
      />
    </div>
  );
}

export function FilterSelect<T extends string>({ value, onChange, options, icon = "filter" }: {
  value: T; onChange: (v: T) => void; options: { value: T; label: string }[]; icon?: "filter" | "sort";
}) {
  return (
    <label className="relative inline-flex items-center">
      <span className="pointer-events-none absolute left-3 text-slate-400">
        {icon === "filter" ? <Filter className="h-3.5 w-3.5" /> : <span className="text-xs">⇅</span>}
      </span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value as T)}
        className="rounded-lg border border-slate-200 bg-white py-2 pr-8 pl-8 text-sm font-medium text-slate-700
          focus:border-brand-500 focus:outline-none"
      >
        {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
    </label>
  );
}

export function Toolbar({ children, shown, total, onRefresh, refreshing }: {
  children?: React.ReactNode; shown?: number; total?: number; onRefresh?: () => void; refreshing?: boolean;
}) {
  return (
    <div className="flex flex-col gap-3 border-b border-slate-100 px-4 py-3 lg:flex-row lg:items-center lg:justify-between">
      <div className="flex flex-1 flex-wrap items-center gap-2">{children}</div>
      <div className="flex items-center gap-3 text-sm text-slate-500">
        {total !== undefined && (
          <span>Showing <b className="text-slate-800">{shown}</b> of <b className="text-slate-800">{total}</b> records</span>
        )}
        {onRefresh && (
          <Button size="sm" onClick={onRefresh} icon={<RefreshCw className={cn("h-3.5 w-3.5", refreshing && "animate-spin")} />}>
            Refresh
          </Button>
        )}
      </div>
    </div>
  );
}

export function Pagination({ page, pageSize, total, onPage, onPageSize, noun = "records" }: {
  page: number; pageSize: number; total: number; onPage: (p: number) => void; onPageSize?: (n: number) => void;
  noun?: string;
}) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  const from = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const to = Math.min(total, page * pageSize);
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 px-4 py-3 text-sm text-slate-500">
      <div className="flex items-center gap-4">
        <span>Showing <b className="text-slate-800">{from}</b> to <b className="text-slate-800">{to}</b> of{" "}
          <b className="text-slate-800">{total}</b> {noun}</span>
        {onPageSize && (
          <label className="flex items-center gap-2 border-l border-slate-200 pl-4">
            Rows:
            <select value={pageSize} onChange={(e) => onPageSize(Number(e.target.value))}
              className="rounded-md border border-slate-200 px-2 py-1 text-slate-700">
              {[10, 25, 50, 100].map((n) => <option key={n} value={n}>{n} / page</option>)}
            </select>
          </label>
        )}
      </div>
      <div className="flex items-center gap-1">
        <Button size="sm" variant="ghost" disabled={page <= 1} onClick={() => onPage(page - 1)} aria-label="Previous page">
          <ChevronLeft className="h-4 w-4" />
        </Button>
        <span className="px-2">Page {page} of {pages}</span>
        <Button size="sm" variant="ghost" disabled={page >= pages} onClick={() => onPage(page + 1)} aria-label="Next page">
          <ChevronRight className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}
