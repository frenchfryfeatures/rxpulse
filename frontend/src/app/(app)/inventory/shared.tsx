import { Badge } from "@/components/ui/badge";
import type { BatchRow, ExpiryStatus } from "@/lib/api/types";
import { useMe } from "@/lib/auth/MeProvider";
import { dateOnly } from "@/lib/format";

export function ExpiryCell({ row }: { row: Pick<BatchRow, "expiry_date" | "days_to_expiry" | "expiry_status"> }) {
  const d = row.days_to_expiry;
  const tone: Record<ExpiryStatus, string> = {
    expired: "text-rose-600", critical: "text-amber-600", warning: "text-amber-500", ok: "text-slate-400",
  };
  const label = d < 0 ? `Expired ${-d} day${d === -1 ? "" : "s"} ago` : d === 0 ? "Expires today"
    : d <= 90 ? `Expires in ${d} days` : `${Math.round(d / 30)} months left`;
  return (
    <div>
      <p className="text-slate-800">{dateOnly(row.expiry_date)}</p>
      <p className={`text-[11px] font-medium ${tone[row.expiry_status]}`}>{label}</p>
    </div>
  );
}

export function StockStatus({ row }: { row: BatchRow }) {
  if (row.expiry_status === "expired") return <Badge tone="red">Expired</Badge>;
  if (row.qty_available === 0) return <Badge tone="amber">Fully reserved</Badge>;
  if (row.expiry_status === "critical") return <Badge tone="amber">Short-dated</Badge>;
  return <Badge tone="green">Available</Badge>;
}

/** Locations where the user holds `perm` (all active locations when unscoped). */
export function useScopedLocations(perm: string) {
  const { me } = useMe();
  const scopes = (me.permission_scopes as Record<string, (string | null)[]>)[perm] ?? [];
  if (scopes.includes(null)) return me.locations;
  return me.locations.filter((l) => scopes.includes(l.id));
}
