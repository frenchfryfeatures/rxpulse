import { Planned } from "@/components/Planned";

export default function Page() {
  return <Planned title="AI Studio" subtitle="RxPulse Orchestrator and specialist agents" phase="Phase 4" anyOf={["ai:chat"]} features={[
    "Chat with the RxPulse Orchestrator, which routes to Pharmacy, Procurement, Consignment IOL, Surgery BOM, Intra-Op, Billing and Analytics agents",
    "Agents act with your permissions only, never more",
    "Proposed actions (draft POs, restock requests, write-offs) wait for your approval",
    "Every agent tool call is audited as actor type “agent” on your behalf",
  ]} />;
}
