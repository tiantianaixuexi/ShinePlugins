import { Link } from "react-router-dom";
import { Command, Search } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useBackendHealth } from "@/hooks/use-backend";
import { cn } from "@/lib/utils";

interface TopbarProps {
  title: string;
  description?: string;
}

export function Topbar({ title, description }: TopbarProps) {
  const { status, data, isFetching } = useBackendHealth();

  const statusLabel =
    status === "online" ? "在线" : status === "connecting" ? "连接中" : "离线";

  return (
    <header className="flex h-14 shrink-0 items-center gap-3 border-b bg-background/80 px-4 backdrop-blur">
      <div className="min-w-0">
        <h1 className="truncate text-sm font-semibold tracking-tight">{title}</h1>
        {description && (
          <p className="truncate text-xs text-muted-foreground">{description}</p>
        )}
      </div>

      <div className="ml-auto flex items-center gap-2">
        <div className="hidden h-8 w-64 items-center gap-2 rounded-md border bg-muted/40 px-2.5 text-xs text-muted-foreground md:flex">
          <Search className="size-3.5" />
          <span className="truncate">搜索项目、章节、人物…</span>
          <kbd className="ml-auto inline-flex items-center gap-0.5 rounded border bg-background px-1 py-0.5 font-sans text-[10px]">
            <Command className="size-2.5" />K
          </kbd>
        </div>

        <Badge
          variant={status === "online" ? "success" : status === "connecting" ? "warning" : "destructive"}
          className={cn("gap-1.5", isFetching && status === "online" && "opacity-70")}
        >
          <span
            className={cn(
              "size-1.5 rounded-full",
              status === "online"
                ? "bg-emerald-500"
                : status === "connecting"
                  ? "animate-pulse-soft bg-amber-500"
                  : "bg-destructive",
            )}
          />
          {statusLabel}
          {status === "online" && data?.version ? (
            <span className="text-emerald-700/80 dark:text-emerald-400/80">v{data.version}</span>
          ) : null}
        </Badge>

        <Button asChild variant="ghost" size="sm" className="hidden sm:inline-flex">
          <Link to="/settings">设置</Link>
        </Button>
      </div>
    </header>
  );
}