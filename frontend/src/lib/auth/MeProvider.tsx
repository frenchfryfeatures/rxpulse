"use client";

import { useQuery } from "@tanstack/react-query";
import { createContext, useContext, useMemo } from "react";
import { ApiError, useApi } from "@/lib/api/client";
import type { Me } from "@/lib/api/types";

type MeContextValue = {
  me: Me;
  /** UX-only permission check; the API is the real enforcement point. */
  can: (permission: string, locationId?: string | null) => boolean;
  canAny: (...permissions: string[]) => boolean;
  primaryRole: string;
};

const MeContext = createContext<MeContextValue | null>(null);

export function useMe(): MeContextValue {
  const v = useContext(MeContext);
  if (!v) throw new Error("useMe must be used inside <MeProvider>");
  return v;
}

export function usePermission(permission: string, locationId?: string | null): boolean {
  return useMe().can(permission, locationId);
}

export function useMeQuery(enabled: boolean) {
  const api = useApi();
  return useQuery({
    queryKey: ["me"],
    queryFn: () => api<Me>("/me"),
    enabled,
    retry: (count, e) => !(e instanceof ApiError && [401, 403].includes(e.status)) && count < 2,
    staleTime: 60_000,
    refetchOnWindowFocus: true, // picks up role changes / deactivation quickly
  });
}

export function MeProvider({ me, children }: { me: Me; children: React.ReactNode }) {
  const value = useMemo<MeContextValue>(() => {
    const scopes = me.permission_scopes as Record<string, (string | null)[]>;
    const can = (perm: string, locationId?: string | null) => {
      const s = scopes[perm];
      if (!s || s.length === 0) return false;
      if (!locationId) return true;
      return s.includes(null) || s.includes(locationId);
    };
    return {
      me,
      can,
      canAny: (...perms: string[]) => perms.some((p) => can(p)),
      primaryRole: me.user.roles[0]?.role_name ?? "No role",
    };
  }, [me]);
  return <MeContext.Provider value={value}>{children}</MeContext.Provider>;
}
