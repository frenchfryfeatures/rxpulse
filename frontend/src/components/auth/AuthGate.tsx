"use client";

import { useQueryClient } from "@tanstack/react-query";
import { ShieldAlert } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useRef } from "react";
import { ApiError, errorMessage } from "@/lib/api/client";
import { FullPageMessage, useAuth } from "@/lib/auth/AuthProvider";
import { MeProvider, useMeQuery } from "@/lib/auth/MeProvider";
import { config } from "@/lib/config";

/** Protects the (app) route group: requires sign-in and an active, provisioned RxPulse account. */
export function AuthGate({ children }: { children: React.ReactNode }) {
  const auth = useAuth();
  const router = useRouter();
  const signedIn = auth.ready && !!auth.account;
  const me = useMeQuery(signedIn);

  useEffect(() => {
    if (auth.ready && !auth.account) router.replace("/login");
  }, [auth.ready, auth.account, router]);

  useIdleLogout(signedIn);

  if (!auth.ready || !auth.account) return <FullPageMessage title="Checking your session…" />;
  if (me.isPending) return <FullPageMessage title="Loading your workspace…" />;
  if (me.isError) {
    const e = me.error;
    const blocked = e instanceof ApiError && ["ACCOUNT_NOT_PROVISIONED", "ACCOUNT_DEACTIVATED"].includes(e.code);
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-50 p-6">
        <div className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-8 text-center shadow-sm">
          <ShieldAlert className="mx-auto h-10 w-10 text-rose-500" />
          <h1 className="mt-4 text-lg font-semibold text-slate-900">
            {blocked ? "Access not available" : "Could not load your account"}
          </h1>
          <p className="mt-2 text-sm text-slate-600">{errorMessage(e)}</p>
          <p className="mt-1 text-xs text-slate-400">Signed in as {auth.account.username}</p>
          <div className="mt-6 flex justify-center gap-2">
            {!blocked && (
              <button onClick={() => me.refetch()} className="rounded-lg border border-slate-200 px-4 py-2 text-sm">
                Retry
              </button>
            )}
            <button onClick={() => auth.logout()} className="rounded-lg bg-slate-900 px-4 py-2 text-sm text-white">
              Sign out
            </button>
          </div>
        </div>
      </div>
    );
  }
  return <MeProvider me={me.data}>{children}</MeProvider>;
}

/** Signs the user out after a period of inactivity (shared OT / nurse-station terminals). */
function useIdleLogout(active: boolean) {
  const { logout } = useAuth();
  const qc = useQueryClient();
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => {
    if (!active || config.idleTimeoutMinutes <= 0) return;
    const reset = () => {
      if (timer.current) clearTimeout(timer.current);
      timer.current = setTimeout(() => {
        qc.clear();
        void logout();
      }, config.idleTimeoutMinutes * 60_000);
    };
    const events = ["mousemove", "keydown", "pointerdown", "scroll", "touchstart"] as const;
    events.forEach((ev) => window.addEventListener(ev, reset, { passive: true }));
    reset();
    return () => {
      events.forEach((ev) => window.removeEventListener(ev, reset));
      if (timer.current) clearTimeout(timer.current);
    };
  }, [active, logout, qc]);
}
