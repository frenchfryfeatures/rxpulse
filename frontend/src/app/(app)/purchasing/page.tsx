import { Planned } from "@/components/Planned";

export default function Page() {
  return <Planned title="Purchasing" subtitle="Vendors, purchase orders and goods receipt" phase="Phase 2" anyOf={["po:view"]} features={[
    "Vendor master with GSTIN and lead times",
    "Purchase orders with approval (creator cannot approve their own PO)",
    "GRN against PO lines with batch / expiry capture (stock receipts already work from Inventory → Receive stock)",
    "PAR-level and forecast-driven PO drafts from the Procurement Agent",
  ]} />;
}
