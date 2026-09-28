const inr = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 2 });

export const money = (v: string | number | null | undefined) => (v == null ? "—" : inr.format(Number(v)));

export const dateShort = (v: string | null | undefined) =>
  v ? new Date(v).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" }) : "—";

export const time = (v: string | null | undefined) =>
  v ? new Date(v).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" }) : "";

export const dateTime = (v: string | null | undefined) => (v ? `${dateShort(v)} ${time(v)}` : "—");

export function relative(v: string | null | undefined): string {
  if (!v) return "Never";
  const mins = Math.round((Date.now() - new Date(v).getTime()) / 60_000);
  if (mins < 1) return "Just now";
  if (mins < 60) return `${mins} min ago`;
  const h = Math.round(mins / 60);
  if (h < 24) return `${h} h ago`;
  return dateShort(v);
}

export function downloadCsv(filename: string, rows: (string | number | null | undefined)[][]) {
  const esc = (v: unknown) => {
    const s = v == null ? "" : String(v);
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const blob = new Blob([rows.map((r) => r.map(esc).join(",")).join("\n")], { type: "text/csv" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  URL.revokeObjectURL(a.href);
}

/** Format a date-only ISO string (YYYY-MM-DD) without timezone shifts. */
export function dateOnly(v: string | null | undefined): string {
  if (!v) return "—";
  const [y, m, d] = v.slice(0, 10).split("-");
  return `${Number(d)}/${Number(m)}/${y}`;
}
