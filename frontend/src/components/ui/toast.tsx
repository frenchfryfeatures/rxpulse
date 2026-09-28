"use client";

import { CheckCircle2, XCircle } from "lucide-react";
import { createContext, useCallback, useContext, useState } from "react";

type Toast = { id: number; tone: "success" | "error"; message: string };
const Ctx = createContext<(tone: Toast["tone"], message: string) => void>(() => {});

export const useToast = () => useContext(Ctx);

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const push = useCallback((tone: Toast["tone"], message: string) => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t, { id, tone, message }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 4500);
  }, []);
  return (
    <Ctx.Provider value={push}>
      {children}
      <div className="no-print fixed right-4 bottom-4 z-[60] flex w-80 flex-col gap-2" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} className="flex items-start gap-2 rounded-xl border border-slate-200 bg-white p-3 text-sm shadow-lg">
            {t.tone === "success"
              ? <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" />
              : <XCircle className="mt-0.5 h-4 w-4 shrink-0 text-rose-600" />}
            <span className="text-slate-700">{t.message}</span>
          </div>
        ))}
      </div>
    </Ctx.Provider>
  );
}
