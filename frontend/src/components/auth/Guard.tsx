"use client";

import { Lock } from "lucide-react";
import { Card } from "@/components/ui/card";
import { useMe } from "@/lib/auth/MeProvider";

/** Page-level UX guard. Deep links to a forbidden page show this instead of a broken screen. */
export function Guard({ anyOf, children }: { anyOf: string[]; children: React.ReactNode }) {
  const { canAny } = useMe();
  if (canAny(...anyOf)) return <>{children}</>;
  return (
    <Card className="mx-auto mt-10 max-w-lg p-10 text-center">
      <Lock className="mx-auto h-8 w-8 text-slate-400" />
      <h1 className="mt-3 text-lg font-semibold">You don&apos;t have access to this page</h1>
      <p className="mt-1 text-sm text-slate-500">Requires one of: {anyOf.join(", ")}. Ask an administrator if you need it.</p>
    </Card>
  );
}

/** Renders children only when the user holds `permission` (UX only; the API enforces). */
export function Can({ permission, locationId, children }: {
  permission: string; locationId?: string | null; children: React.ReactNode;
}) {
  const { can } = useMe();
  return can(permission, locationId) ? <>{children}</> : null;
}
