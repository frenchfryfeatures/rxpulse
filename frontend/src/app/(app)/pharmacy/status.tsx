import { Badge, type Tone } from "@/components/ui/badge";
import type { OrderStatus } from "@/lib/api/types";

const MAP: Record<OrderStatus, { tone: Tone; label: string }> = {
  allocated: { tone: "blue", label: "Allocated" },
  dispatched: { tone: "slate", label: "Dispatched" },
  partially_returned: { tone: "amber", label: "Part returned" },
  returned: { tone: "amber", label: "Returned" },
  cancelled: { tone: "red", label: "Cancelled" },
};

export function StatusBadge({ status }: { status: OrderStatus }) {
  const s = MAP[status];
  return <Badge tone={s.tone}>{s.label}</Badge>;
}
