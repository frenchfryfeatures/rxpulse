"use client";

import { useQuery } from "@tanstack/react-query";
import { useApi } from "@/lib/api/client";
import type { Dashboard, Location } from "@/lib/api/types";
import { useMe } from "@/lib/auth/MeProvider";

export function useDashboard() {
  const api = useApi();
  const { can } = useMe();
  return useQuery({
    queryKey: ["dashboard"],
    queryFn: () => api<Dashboard>("/dashboard/summary"),
    enabled: can("dashboard:view") || can("inventory:view"),
    refetchInterval: 60_000,
  });
}

export function useLocations(): Location[] {
  return useMe().me.locations;
}
