import { Construction } from "lucide-react";
import { Guard } from "@/components/auth/Guard";
import { Card, PageHeader } from "@/components/ui/card";

export function Planned({ title, subtitle, phase, anyOf, features }: {
  title: string; subtitle: string; phase: string; anyOf: string[]; features: string[];
}) {
  return (
    <Guard anyOf={anyOf}>
      <PageHeader title={title} subtitle={subtitle} />
      <Card className="p-8">
        <div className="flex items-start gap-4">
          <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-amber-50 text-amber-600"><Construction className="h-5 w-5" /></span>
          <div>
            <p className="text-sm font-semibold text-slate-900">Planned for {phase}</p>
            <p className="mt-1 text-sm text-slate-500">This module is part of the delivery plan (docs/IMPLEMENTATION_PLAN.md). Access is already governed by RBAC.</p>
            <ul className="mt-4 list-disc space-y-1 pl-5 text-sm text-slate-700">{features.map((f) => <li key={f}>{f}</li>)}</ul>
          </div>
        </div>
      </Card>
    </Guard>
  );
}
