import { Planned } from "@/components/Planned";

export default function Page() {
  return <Planned title="Consignment IOL" subtitle="Vendor-owned intraocular lens stock" phase="Phase 3" anyOf={["consignment:view"]} features={[
    "Model × diopter grid of on-hand lenses, serial-level tracking",
    "Reserve at kit allocation, implant at surgery → vendor payable + patient charge",
    "Automatic vendor usage notification and restock request",
  ]} />;
}
