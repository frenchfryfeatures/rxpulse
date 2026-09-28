import { cn } from "./cn";

export function Card({ className, ...rest }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("rounded-2xl border border-slate-200 bg-white", className)} {...rest} />;
}

export function CardHeader({ title, icon, actions, className }: {
  title: React.ReactNode; icon?: React.ReactNode; actions?: React.ReactNode; className?: string;
}) {
  return (
    <div className={cn("flex items-center justify-between gap-3 border-b border-slate-100 px-5 py-4", className)}>
      <h2 className="flex items-center gap-2 text-[15px] font-semibold text-slate-900">
        {icon}
        {title}
      </h2>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  );
}

export function PageHeader({ title, subtitle, actions }: {
  title: string; subtitle?: string; actions?: React.ReactNode;
}) {
  return (
    <Card className="flex flex-col gap-4 px-6 py-6 md:flex-row md:items-center md:justify-between">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-slate-900">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-slate-500">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </Card>
  );
}
