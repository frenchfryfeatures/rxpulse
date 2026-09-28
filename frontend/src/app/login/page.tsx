"use client";

import { useQuery } from "@tanstack/react-query";
import { KeyRound, Loader2, ShieldCheck } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { ErrorBanner } from "@/components/ui/form";
import type { DevUser } from "@/lib/api/types";
import { useAuth } from "@/lib/auth/AuthProvider";
import { config } from "@/lib/config";

export default function LoginPage() {
  const auth = useAuth();
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => {
    if (auth.ready && auth.account) router.replace("/dashboard");
  }, [auth.ready, auth.account, router]);

  const devUsers = useQuery({
    queryKey: ["dev-users"],
    enabled: auth.mode === "dev",
    queryFn: async () => {
      const r = await fetch(`${config.apiBaseUrl}/dev/users`);
      if (!r.ok) throw new Error("Could not load demo accounts. Is the API running with AUTH_MODE=dev?");
      return (await r.json()) as DevUser[];
    },
  });

  const run = async (key: string, fn: () => Promise<void>) => {
    setError(null);
    setBusy(key);
    try {
      await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Sign-in failed");
      setBusy(null);
    }
  };

  return (
    <div className="grid min-h-screen lg:grid-cols-2">
      <div className="hidden flex-col justify-between bg-ink p-12 text-white lg:flex">
        <div className="flex items-center gap-3">
          <span className="grid h-10 w-10 place-items-center rounded-lg bg-white text-sm font-bold text-ink">Rx</span>
          <span className="text-lg font-bold">RxPulse <span className="text-blue-300">IQ</span></span>
        </div>
        <div>
          <h1 className="text-3xl leading-tight font-bold">Pharmacy, surgical supplies and stock for {config.hospitalName}.</h1>
          <p className="mt-4 max-w-md text-slate-300">
            FEFO dispensing for counter sales and doctor/OT requisitions, batch-level expiry tracking, and
            role-based access for every member of staff.
          </p>
        </div>
        <p className="flex items-center gap-2 text-xs text-slate-400">
          <ShieldCheck className="h-4 w-4" /> Every action is recorded in a tamper-evident audit trail.
        </p>
      </div>

      <div className="flex items-center justify-center p-6">
        <div className="w-full max-w-md">
          <h2 className="text-2xl font-bold text-slate-900">Sign in</h2>
          <p className="mt-1 text-sm text-slate-500">Use your hospital Microsoft account.</p>

          <div className="mt-8 space-y-4">
            <ErrorBanner message={error} />
            {auth.mode === "entra" ? (
              <Button variant="primary" className="w-full py-3" loading={busy === "ms"}
                onClick={() => run("ms", auth.loginMicrosoft)}
                icon={<svg viewBox="0 0 21 21" className="h-4 w-4" aria-hidden><path fill="#f25022" d="M1 1h9v9H1z"/><path fill="#7fba00" d="M11 1h9v9h-9z"/><path fill="#00a4ef" d="M1 11h9v9H1z"/><path fill="#ffb900" d="M11 11h9v9h-9z"/></svg>}>
                Sign in with Microsoft
              </Button>
            ) : (
              <div className="rounded-2xl border border-amber-200 bg-amber-50/50 p-4">
                <p className="flex items-center gap-2 text-sm font-semibold text-amber-800">
                  <KeyRound className="h-4 w-4" /> Local development sign-in
                </p>
                <p className="mt-1 text-xs text-amber-700">
                  AUTH_MODE=dev: pick a seeded staff account. Production uses Microsoft Entra ID (MSAL).
                </p>
                <div className="mt-3 max-h-[60vh] space-y-1.5 overflow-y-auto">
                  {devUsers.isPending && <Loader2 className="mx-auto h-5 w-5 animate-spin text-slate-400" />}
                  <ErrorBanner message={devUsers.error?.message} />
                  {devUsers.data?.map((u) => (
                    <button key={u.email} disabled={!!busy}
                      onClick={() => run(u.email, async () => { await auth.loginDev(u.email); router.replace("/dashboard"); })}
                      className="flex w-full items-center justify-between gap-3 rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-left hover:border-slate-300 disabled:opacity-60">
                      <span>
                        <span className="block text-sm font-semibold text-slate-900">{u.display_name}</span>
                        <span className="block text-xs text-slate-500">{u.job_title} · {u.email}</span>
                      </span>
                      <span className="shrink-0 text-right text-[11px] font-medium text-brand-600">
                        {busy === u.email ? <Loader2 className="h-4 w-4 animate-spin" /> : u.roles.join(", ")}
                      </span>
                    </button>
                  ))}
                  <button disabled={!!busy}
                    onClick={() => run("stranger", async () => { await auth.loginDev("stranger@elsewhere.example"); router.replace("/dashboard"); })}
                    className="w-full rounded-xl border border-dashed border-slate-300 px-3 py-2 text-xs text-slate-500 hover:bg-white">
                    Try an account that hasn&apos;t been added to RxPulse
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
