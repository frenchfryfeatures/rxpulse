"use client";

import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { Guard } from "@/components/auth/Guard";
import { Card, PageHeader } from "@/components/ui/card";
import { Tabs } from "@/components/ui/tabs";
import { useDashboard } from "@/lib/queries";
import { BatchesTab } from "./BatchesTab";
import { CatalogTab } from "./CatalogTab";
import { ExpiryTab } from "./ExpiryTab";
import { FefoTab } from "./FefoTab";
import { MovementsTab } from "./MovementsTab";

type Tab = "batches" | "catalog" | "fefo" | "expiry" | "movements";

export default function InventoryPage() {
  return (
    <Guard anyOf={["inventory:view"]}>
      <Suspense>
        <Inventory />
      </Suspense>
    </Guard>
  );
}

function Inventory() {
  const params = useSearchParams();
  const [tab, setTab] = useState<Tab>((params.get("tab") as Tab) ?? "batches");
  const dash = useDashboard();
  return (
    <>
      <PageHeader title="Inventory & Batches"
        subtitle="Batch-level stock across the central store, pharmacy and OT store, with FEFO allocation and expiry tracking" />
      <Card className="px-6 pt-4">
        <Tabs<Tab> value={tab} onChange={setTab} tabs={[
          { value: "batches", label: "All Active Batches", count: dash.data?.active_batches ?? undefined },
          { value: "catalog", label: "Medicines & Consumables" },
          { value: "fefo", label: "FEFO Allocation Engine" },
          { value: "expiry", label: "Expiry Risk Analysis" },
          { value: "movements", label: "Stock Movements" },
        ]} />
        <div className="-mx-6 mt-0">
          {tab === "batches" && <BatchesTab initialQ={params.get("q") ?? ""} initialExpiry={params.get("expiry") ?? "all"} />}
          {tab === "catalog" && <CatalogTab />}
          {tab === "fefo" && <FefoTab />}
          {tab === "expiry" && <ExpiryTab />}
          {tab === "movements" && <MovementsTab />}
        </div>
      </Card>
    </>
  );
}
