"use client";

import { InteractionRequiredAuthError, type PublicClientApplication } from "@azure/msal-browser";
import { MsalProvider } from "@azure/msal-react";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, useSyncExternalStore } from "react";
import { config } from "@/lib/config";
import { apiScopes, getMsal } from "./msal";

export type Account = { name: string; username: string };

export type AuthSession = {
  mode: "entra" | "dev";
  ready: boolean;
  account: Account | null;
  /** Returns a bearer token for the RxPulse API, or null if the user must sign in. */
  getToken: (forceRefresh?: boolean) => Promise<string | null>;
  loginMicrosoft: () => Promise<void>;
  loginDev: (email: string) => Promise<void>;
  logout: () => Promise<void>;
};

const AuthContext = createContext<AuthSession | null>(null);

export function useAuth(): AuthSession {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}

// ----------------------------------------------------------------------------- Entra (MSAL)
function EntraSession({ pca, children }: { pca: PublicClientApplication; children: React.ReactNode }) {
  const [account, setAccount] = useState<Account | null>(() => toAccount(pca));

  useEffect(() => {
    const id = pca.addEventCallback(() => setAccount(toAccount(pca)));
    return () => {
      if (id) pca.removeEventCallback(id);
    };
  }, [pca]);

  const getToken = useCallback(
    async (forceRefresh = false) => {
      const active = pca.getActiveAccount();
      if (!active) return null;
      try {
        const res = await pca.acquireTokenSilent({ scopes: apiScopes, account: active, forceRefresh });
        return res.accessToken;
      } catch (e) {
        if (e instanceof InteractionRequiredAuthError) {
          await pca.acquireTokenRedirect({ scopes: apiScopes, account: active });
          return null;
        }
        throw e;
      }
    },
    [pca],
  );

  const session = useMemo<AuthSession>(
    () => ({
      mode: "entra",
      ready: true,
      account,
      getToken,
      loginMicrosoft: () => pca.loginRedirect({ scopes: ["openid", "profile", ...apiScopes], prompt: "select_account" }),
      loginDev: async () => {
        throw new Error("Dev sign-in is disabled");
      },
      logout: () => pca.logoutRedirect({ account: pca.getActiveAccount() }),
    }),
    [account, getToken, pca],
  );

  return (
    <MsalProvider instance={pca}>
      <AuthContext.Provider value={session}>{children}</AuthContext.Provider>
    </MsalProvider>
  );
}

function toAccount(pca: PublicClientApplication): Account | null {
  const a = pca.getActiveAccount();
  return a ? { name: a.name ?? a.username, username: a.username } : null;
}

function EntraProvider({ children }: { children: React.ReactNode }) {
  const [pca, setPca] = useState<PublicClientApplication | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    getMsal().then(setPca, (e: unknown) => setError(e instanceof Error ? e.message : String(e)));
  }, []);
  if (error) return <FullPageMessage title="Sign-in is unavailable" body={error} />;
  if (!pca) return <FullPageMessage title="Loading…" />;
  return <EntraSession pca={pca}>{children}</EntraSession>;
}

// ----------------------------------------------------------------------------- Dev sign-in
const DEV_KEY = "rxpulse.dev.session";

type DevStored = { token: string; expiresAt: number; account: Account };

const devListeners = new Set<() => void>();
const notifyDev = () => devListeners.forEach((l) => l());
function subscribeDev(cb: () => void) {
  devListeners.add(cb);
  window.addEventListener("storage", cb);
  return () => {
    devListeners.delete(cb);
    window.removeEventListener("storage", cb);
  };
}
const devSnapshot = () => sessionStorage.getItem(DEV_KEY);
const devServerSnapshot = () => undefined; // not known during server render

function parseDev(raw: string | null | undefined): DevStored | null {
  if (!raw) return null;
  try {
    const v = JSON.parse(raw) as DevStored;
    return v.expiresAt > Date.now() + 30_000 ? v : null;
  } catch {
    return null;
  }
}

function DevProvider({ children }: { children: React.ReactNode }) {
  const raw = useSyncExternalStore(subscribeDev, devSnapshot, devServerSnapshot);
  const ready = raw !== undefined;
  const stored = useMemo(() => parseDev(raw), [raw]);

  const session = useMemo<AuthSession>(
    () => ({
      mode: "dev",
      ready,
      account: stored?.account ?? null,
      getToken: async () => parseDev(sessionStorage.getItem(DEV_KEY))?.token ?? null,
      loginMicrosoft: async () => {
        throw new Error("Microsoft sign-in is not configured (NEXT_PUBLIC_AUTH_MODE=dev)");
      },
      loginDev: async (email: string) => {
        const res = await fetch(`${config.apiBaseUrl}/dev/token`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email }),
        });
        if (!res.ok) throw new Error("Dev sign-in failed");
        const body = (await res.json()) as { access_token: string; expires_in: number };
        const v: DevStored = {
          token: body.access_token,
          expiresAt: Date.now() + body.expires_in * 1000,
          account: { name: email, username: email },
        };
        sessionStorage.setItem(DEV_KEY, JSON.stringify(v));
        notifyDev();
      },
      logout: async () => {
        // AuthGate sends the user to /login once the account is gone.
        sessionStorage.removeItem(DEV_KEY);
        notifyDev();
      },
    }),
    [ready, stored],
  );
  return <AuthContext.Provider value={session}>{children}</AuthContext.Provider>;
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  return config.authMode === "dev" ? <DevProvider>{children}</DevProvider> : <EntraProvider>{children}</EntraProvider>;
}

export function FullPageMessage({ title, body }: { title: string; body?: string }) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 p-6">
      <div className="text-center">
        <p className="text-sm font-semibold text-slate-800">{title}</p>
        {body && <p className="mt-1 text-sm text-slate-500">{body}</p>}
      </div>
    </div>
  );
}
