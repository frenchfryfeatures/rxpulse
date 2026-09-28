import {
  BarChart3, Eye, FileText, LayoutGrid, type LucideIcon, Package, Pill, Scissors, Settings,
  ShieldCheck, ShoppingCart, Sparkles, Users,
} from "lucide-react";

export type NavItem = {
  href: string;
  label: string;
  icon: LucideIcon;
  /** Shown if the user holds any of these permissions. */
  anyOf: string[];
  badge?: "batches" | "agent";
  planned?: string; // delivery phase for modules not built yet
};

export const NAV: NavItem[] = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutGrid, anyOf: ["dashboard:view"] },
  { href: "/ai-studio", label: "AI Studio", icon: Sparkles, anyOf: ["ai:chat"], badge: "agent", planned: "Phase 4" },
  { href: "/inventory", label: "Inventory", icon: Package, anyOf: ["inventory:view"], badge: "batches" },
  { href: "/pharmacy", label: "Pharmacy", icon: Pill,
    anyOf: ["pharmacy_order:view", "pharmacy_order:create", "requisition:create"] },
  { href: "/purchasing", label: "Purchasing", icon: ShoppingCart, anyOf: ["po:view"], planned: "Phase 2" },
  { href: "/surgery", label: "Surgery & OT", icon: Scissors, anyOf: ["surgery:view"], planned: "Phase 3" },
  { href: "/consignment", label: "Consignment IOL", icon: Eye, anyOf: ["consignment:view"], planned: "Phase 3" },
  { href: "/billing", label: "Billing", icon: FileText, anyOf: ["billing:view"], planned: "Phase 3" },
  { href: "/reports", label: "Reports", icon: BarChart3, anyOf: ["reports:view"], planned: "Phase 5" },
  { href: "/staff", label: "Staff & Roles", icon: Users, anyOf: ["staff:view"] },
  { href: "/audit", label: "Audit Trail", icon: ShieldCheck, anyOf: ["audit:view"] },
  { href: "/settings", label: "Settings", icon: Settings, anyOf: ["settings:manage"], planned: "Phase 6" },
];

export const firstAllowed = (canAny: (...p: string[]) => boolean) =>
  NAV.find((n) => canAny(...n.anyOf) && !n.planned)?.href ?? "/dashboard";

