"use client";

import { useCallback } from "react";
import { useAuth } from "@/lib/auth/AuthProvider";
import { config } from "@/lib/config";

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public body: Record<string, unknown> = {},
  ) {
    super(message);
  }
}

type Query = Record<string, string | number | boolean | null | undefined>;
export type RequestOptions = { method?: string; body?: unknown; query?: Query };

function buildUrl(path: string, query?: Query): string {
  const url = new URL(config.apiBaseUrl + path);
  for (const [k, v] of Object.entries(query ?? {})) {
    if (v !== undefined && v !== null && v !== "") url.searchParams.set(k, String(v));
  }
  return url.toString();
}

/** Returns a fetcher bound to the signed-in user. Retries once with a fresh token on 401. */
export function useApi() {
  const { getToken } = useAuth();
  return useCallback(
    async <T,>(path: string, opts: RequestOptions = {}): Promise<T> => {
      const send = async (force: boolean) => {
        const token = await getToken(force);
        if (!token) throw new ApiError(401, "NOT_SIGNED_IN", "Please sign in again");
        return fetch(buildUrl(path, opts.query), {
          method: opts.method ?? "GET",
          headers: {
            Authorization: `Bearer ${token}`,
            ...(opts.body !== undefined ? { "Content-Type": "application/json" } : {}),
          },
          body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
        });
      };
      let res = await send(false);
      if (res.status === 401) res = await send(true);
      if (res.status === 204) return undefined as T;
      const text = await res.text();
      const data = text ? JSON.parse(text) : undefined;
      if (!res.ok) {
        const body = (data ?? {}) as Record<string, unknown>;
        throw new ApiError(
          res.status,
          String(body.code ?? "ERROR"),
          String(body.message ?? `Request failed (${res.status})`),
          body,
        );
      }
      return data as T;
    },
    [getToken],
  );
}

export function errorMessage(e: unknown): string {
  if (e instanceof ApiError) {
    if (e.status === 403 && e.code === "FORBIDDEN" && Array.isArray(e.body.missing) && e.body.missing.length) {
      return `${e.message} (requires ${(e.body.missing as string[]).join(", ")})`;
    }
    return e.message;
  }
  if (e instanceof TypeError) return "Cannot reach the RxPulse API. Check your connection.";
  return e instanceof Error ? e.message : "Something went wrong";
}
