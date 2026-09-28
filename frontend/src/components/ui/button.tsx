import { Loader2 } from "lucide-react";
import { forwardRef } from "react";
import { cn } from "./cn";

type Variant = "primary" | "secondary" | "danger" | "ghost" | "outline-brand" | "outline-danger" | "outline-warn";

const variants: Record<Variant, string> = {
  primary: "bg-ink text-white hover:bg-slate-800 border border-ink",
  secondary: "bg-white text-slate-700 border border-slate-200 hover:bg-slate-50",
  danger: "bg-rose-600 text-white border border-rose-600 hover:bg-rose-700",
  ghost: "text-slate-600 hover:bg-slate-100 border border-transparent",
  "outline-brand": "bg-white text-brand-600 border border-brand-100 hover:bg-brand-50",
  "outline-danger": "bg-white text-rose-600 border border-rose-200 hover:bg-rose-50",
  "outline-warn": "bg-white text-amber-700 border border-amber-200 hover:bg-amber-50",
};

export type ButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant;
  size?: "sm" | "md";
  loading?: boolean;
  icon?: React.ReactNode;
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "secondary", size = "md", loading, icon, className, children, disabled, ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      disabled={disabled || loading}
      className={cn(
        "inline-flex items-center justify-center gap-1.5 rounded-lg font-medium whitespace-nowrap transition-colors",
        "disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-brand-500",
        size === "sm" ? "px-2.5 py-1.5 text-xs" : "px-3.5 py-2 text-sm",
        variants[variant],
        className,
      )}
      {...rest}
    >
      {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : icon}
      {children}
    </button>
  );
});
