import { Planned } from "@/components/Planned";

export default function Page() {
  return <Planned title="Billing & Reconciliation" subtitle="Bill patients for what was actually used" phase="Phase 3" anyOf={["billing:view"]} features={[
    "Allocated vs used vs returned reconciliation per surgery case",
    "GST-compliant patient invoices (pharmacy counter invoices are already issued on dispatch)",
    "Vendor payables for implanted consignment IOLs",
  ]} />;
}
