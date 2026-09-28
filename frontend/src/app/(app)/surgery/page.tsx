import { Planned } from "@/components/Planned";

export default function Page() {
  return <Planned title="Surgery & OT" subtitle="Procedure BOMs, surgery kits and intra-operative usage" phase="Phase 3" anyOf={["surgery:view"]} features={[
    "Procedure bills of materials (Phaco, MSICS, vitrectomy, intravitreal injection, …)",
    "Kit allocation by FEFO with IOL power matching, issue to OT by barcode scan",
    "Tablet-first intra-op logging: opened / used / wasted per item",
    "Return of unused items and hand-off to billing reconciliation",
  ]} />;
}
