"use client";

import { X } from "lucide-react";
import { useEffect, useRef } from "react";
import { Button } from "./button";
import { cn } from "./cn";
import { ErrorBanner } from "./form";

export function Dialog({ open, onClose, title, description, children, footer, size = "md" }: {
  open: boolean;
  onClose: () => void;
  title: React.ReactNode;
  description?: React.ReactNode;
  children?: React.ReactNode;
  footer?: React.ReactNode;
  size?: "sm" | "md" | "lg" | "xl";
}) {
  const panel = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    panel.current?.focus();
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);
  if (!open) return null;
  const width = { sm: "max-w-md", md: "max-w-xl", lg: "max-w-3xl", xl: "max-w-5xl" }[size];
  return (
    <div className="no-print fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-slate-900/40 p-4 sm:p-8">
      <div
        ref={panel}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-label={typeof title === "string" ? title : undefined}
        className={cn("w-full rounded-2xl bg-white shadow-xl outline-none", width)}
      >
        <div className="flex items-start justify-between gap-4 border-b border-slate-100 px-6 py-4">
          <div>
            <h2 className="text-base font-semibold text-slate-900">{title}</h2>
            {description && <p className="mt-0.5 text-sm text-slate-500">{description}</p>}
          </div>
          <button onClick={onClose} className="rounded-md p-1 text-slate-400 hover:bg-slate-100" aria-label="Close">
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="px-6 py-5">{children}</div>
        {footer && <div className="flex justify-end gap-2 border-t border-slate-100 px-6 py-4">{footer}</div>}
      </div>
    </div>
  );
}

/** In-app confirmation (never window.confirm): shows what will happen and surfaces API errors inline. */
export function ConfirmDialog({ open, onClose, onConfirm, title, children, confirmLabel = "Confirm", tone = "primary",
  loading, error }: {
  open: boolean;
  onClose: () => void;
  onConfirm: () => void;
  title: string;
  children?: React.ReactNode;
  confirmLabel?: string;
  tone?: "primary" | "danger";
  loading?: boolean;
  error?: string | null;
}) {
  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={title}
      size="sm"
      footer={
        <>
          <Button onClick={onClose} disabled={loading}>Cancel</Button>
          <Button variant={tone} onClick={onConfirm} loading={loading}>{confirmLabel}</Button>
        </>
      }
    >
      <div className="space-y-3 text-sm text-slate-600">
        {children}
        <ErrorBanner message={error} />
      </div>
    </Dialog>
  );
}
