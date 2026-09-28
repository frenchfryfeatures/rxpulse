import { AuthGate } from "@/components/auth/AuthGate";
import { Sidebar } from "@/components/shell/Sidebar";
import { TopBar } from "@/components/shell/TopBar";

export default function AppLayout({ children }: LayoutProps<"/">) {
  return (
    <AuthGate>
      <div className="flex min-h-screen">
        <Sidebar />
        <div className="flex min-w-0 flex-1 flex-col">
          <TopBar />
          <main className="mx-auto w-full max-w-[1500px] flex-1 space-y-6 p-6">{children}</main>
        </div>
      </div>
    </AuthGate>
  );
}
