import { Outlet, useLocation } from "react-router-dom";
import { TriangleAlert } from "lucide-react";

import { Sidebar } from "@/components/layout/sidebar";
import { StatusBar } from "@/components/layout/status-bar";
import { Topbar } from "@/components/layout/topbar";
import { Button } from "@/components/ui/button";
import { findNavItem } from "@/config/navigation";
import { useBackendHealth } from "@/hooks/use-backend";
import { BACKEND_UNREACHABLE_MESSAGE } from "@/lib/api";

export function AppShell() {
  const { pathname } = useLocation();
  const current = findNavItem(pathname);
  const health = useBackendHealth();

  return (
    <div className="flex h-dvh w-full overflow-hidden bg-background">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar title={current?.label ?? "工作台"} description={current?.description} />

        {health.status === "offline" && (
          <div className="flex items-center gap-2 border-b border-amber-500/30 bg-amber-500/10 px-4 py-1.5 text-xs text-amber-800 dark:text-amber-300">
            <TriangleAlert className="size-3.5 shrink-0" />
            <span className="min-w-0 flex-1 truncate" title={BACKEND_UNREACHABLE_MESSAGE}>
              {BACKEND_UNREACHABLE_MESSAGE}
            </span>
            <Button
              size="sm"
              variant="ghost"
              className="h-6 shrink-0 px-2 text-xs"
              onClick={() => void health.refetch()}
            >
              重试
            </Button>
          </div>
        )}

        <main className="min-h-0 flex-1 overflow-y-auto">
          <Outlet />
        </main>
        <StatusBar />
      </div>
    </div>
  );
}