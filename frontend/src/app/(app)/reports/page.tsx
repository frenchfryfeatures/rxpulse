import { Planned } from "@/components/Planned";

export default function Page() {
  return <Planned title="Reports & Analytics" subtitle="Consumption, expiry loss, pharmacy sales and forecasts" phase="Phase 5" anyOf={["reports:view"]} features={[
    "Pharmacy counter sales trends, dead stock and margin analysis",
    "Expiry loss and procedure costing",
    "Seasonal demand forecasts and burn-rate alerts",
    "CSV / XLSX export",
  ]} />;
}
