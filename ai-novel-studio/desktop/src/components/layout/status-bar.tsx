import { useMemo } from "react";
import { useLocation } from "react-router-dom";
import { Database, HardDrive, Wifi } from "lucide-react";

import { findNavItem } from "@/config/navigation";
import { useBackendHealth } from "@/hooks/use-backend";
import { useStudioStats } from "@/hooks/use-backend";
import { formatNumber } from "@/lib/utils";

/**
 * Thin status strip: which module is open, backend health and aggregate
 * counters. Deliberately cheap so it never blocks rendering.
 */
export function StatusBar() {
  const { pathname } = useLocation();
  const item = findNavItem(pathname);
  const { status, data } = useBackendHealth();
  const stats = useStudioStats();

  const totals = stats.data?.totals;
  const labels = useMemo(
    () => [
      { icon: Database, text: `${formatNumber(totals?.projects ?? 0)} 个项目` },
      { icon: HardDrive, text: `${formatNumber(totals?.words ?? 0)} 字` },
    ],
    [totals],
  );

  return (
    <footer className="flex h-8 shrink-0 items-center gap-3 border-t bg-muted/30 px-4 text-[11px] text-muted-foreground">
      <span className="inline-flex items-center gap-1">
        <Wifi className="size-3" />
        {status === "online" ? "已连接" : status === "connecting" ? "连接中" : "未连接"}
      </span>
      {data?.schema_version ? <span>schema v{data.schema_version}</span> : null}
      <span className="ml-auto flex items-center gap-3">
        {labels.map(({ icon: Icon, text }) => (
          <span key={text} className="inline-flex items-center gap-1">
            <Icon className="size-3" />
            {text}
          </span>
        ))}
        {item?.milestone ? <span>{item.milestone}</span> : null}
      </span>
    </footer>
  );
}