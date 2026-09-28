import { Planned } from "@/components/Planned";

export default function Page() {
  return <Planned title="Settings" subtitle="Locations, thresholds and integrations" phase="Phase 6" anyOf={["settings:manage"]} features={[
    "Locations and bins",
    "Minimum shelf life, PAR defaults and idle sign-out timeout",
    "Vendor notification channels and AI provider settings",
  ]} />;
}
