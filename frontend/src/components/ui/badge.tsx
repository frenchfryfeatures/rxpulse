import { cn } from "./cn";

export type Tone = "green" | "red" | "amber" | "blue" | "slate" | "violet";

const tones: Record<Tone, string> = {
  green: "border-emerald-200 bg-emerald-50 text-emerald-700",
  red: "border-rose-200 bg-rose-50 text-rose-700",
  amber: "border-amber-200 bg-amber-50 text-amber-700",
  blue: "border-blue-200 bg-blue-50 text-blue-700",
  slate: "border-slate-200 bg-slate-50 text-slate-600",
  violet: "border-violet-200 bg-violet-50 text-violet-700",
};

export function Badge({ tone = "slate", className, children, uppercase = true }: {
  tone?: Tone; className?: string; children: React.ReactNode; uppercase?: boolean;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-md border px-2 py-0.5 text-[11px] font-semibold",
        uppercase && "tracking-wide uppercase",
        tones[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

export function Chip({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <span className={cn("inline-flex items-center rounded border border-blue-100 bg-blue-50/60 px-1.5 py-0.5 " +
      "font-mono text-[11px] text-blue-700", className)}>
      {children}
    </span>
  );
}
