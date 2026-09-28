import { cn } from "./cn";

export function Tabs<T extends string>({ tabs, value, onChange }: {
  tabs: { value: T; label: string; count?: number; hidden?: boolean }[];
  value: T;
  onChange: (v: T) => void;
}) {
  return (
    <div role="tablist" className="flex gap-6 overflow-x-auto border-b border-slate-200">
      {tabs.filter((t) => !t.hidden).map((t) => (
        <button
          key={t.value}
          role="tab"
          aria-selected={value === t.value}
          onClick={() => onChange(t.value)}
          className={cn(
            "-mb-px flex items-center gap-2 border-b-2 px-0.5 pb-3 text-sm font-medium whitespace-nowrap",
            value === t.value ? "border-ink text-slate-900" : "border-transparent text-slate-400 hover:text-slate-600",
          )}
        >
          {t.label}
          {t.count !== undefined && (
            <span className={cn("rounded-full px-2 py-0.5 text-[11px] font-semibold",
              value === t.value ? "bg-ink text-white" : "bg-slate-100 text-slate-500")}>
              {t.count}
            </span>
          )}
        </button>
      ))}
    </div>
  );
}
