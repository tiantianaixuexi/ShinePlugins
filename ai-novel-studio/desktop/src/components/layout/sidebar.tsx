import { NavLink, useLocation } from "react-router-dom";
import {
  ChevronsLeft,
  ChevronsRight,
  Feather,
  CircleDot,
  Sparkles,
} from "lucide-react";

import { NAV_GROUPS, NAV_ITEMS, findNavItem } from "@/config/navigation";
import { useBackendHealth } from "@/hooks/use-backend";
import { useTheme } from "@/hooks/use-theme";
import { useUiStore } from "@/stores/ui";
import { cn } from "@/lib/utils";
import { Moon, Sun } from "lucide-react";

export function Sidebar() {
  const collapsed = useUiStore((state) => state.sidebarCollapsed);
  const toggle = useUiStore((state) => state.toggleSidebar);
  const { theme, toggle: toggleTheme } = useTheme();
  const { status } = useBackendHealth();
  const location = useLocation();
  const current = findNavItem(location.pathname);

  return (
    <aside
      className={cn(
        "flex h-full shrink-0 flex-col border-r border-sidebar-border bg-sidebar transition-[width] duration-200",
        collapsed ? "w-[68px]" : "w-[248px]",
      )}
    >
      <div className="flex h-14 items-center gap-2.5 px-3">
        <div className="grid size-8 shrink-0 place-items-center rounded-lg bg-primary text-primary-foreground shadow-sm">
          <Feather className="size-4" />
        </div>
        {!collapsed && (
          <div className="min-w-0 leading-tight">
            <div className="truncate text-sm font-semibold tracking-tight">AI Novel Studio</div>
            <div className="truncate text-[11px] text-muted-foreground">长篇小说创作工作站</div>
          </div>
        )}
      </div>

      <nav className="flex min-h-0 flex-1 flex-col gap-1 overflow-y-auto px-2 pb-2">
        {NAV_GROUPS.map((group) => {
          const items = NAV_ITEMS.filter((item) => item.group === group);
          if (items.length === 0) return null;
          return (
            <div key={group} className="flex flex-col gap-1">
              {!collapsed && (
                <div className="px-2 pb-0.5 pt-2 text-[11px] font-medium uppercase tracking-wider text-muted-foreground/70">
                  {group}
                </div>
              )}
              {items.map((item) => {
                const Icon = item.icon;
                const active = current?.path === item.path;
                return (
                  <NavLink
                    key={item.path}
                    to={item.path}
                    end={item.path === "/"}
                    title={collapsed ? item.label : undefined}
                    className={cn(
                      "group relative flex items-center gap-2.5 rounded-md px-2 py-2 text-sm transition-colors",
                      "hover:bg-sidebar-accent hover:text-sidebar-accent-foreground",
                      active
                        ? "bg-sidebar-accent font-medium text-sidebar-accent-foreground"
                        : "text-sidebar-foreground/85",
                    )}
                  >
                    <Icon
                      className={cn(
                        "size-4 shrink-0",
                        active ? "text-primary" : "text-muted-foreground group-hover:text-foreground",
                      )}
                    />
                    {!collapsed && (
                      <>
                        <span className="truncate">{item.label}</span>
                        {!item.implemented && (
                          <CircleDot className="ml-auto size-3 text-muted-foreground/50" />
                        )}
                      </>
                    )}
                    {collapsed && !item.implemented && (
                      <CircleDot className="absolute right-1 top-1 size-2 text-muted-foreground/40" />
                    )}
                  </NavLink>
                );
              })}
            </div>
          );
        })}
      </nav>

      <div className="border-t border-sidebar-border p-2">
        <div
          className={cn(
            "flex items-center gap-2 rounded-md px-2 py-1.5 text-xs",
            collapsed && "justify-center px-0",
          )}
        >
          <span
            className={cn(
              "size-2 shrink-0 rounded-full",
              status === "online"
                ? "bg-emerald-500"
                : status === "connecting"
                  ? "animate-pulse-soft bg-amber-500"
                  : "bg-destructive",
            )}
          />
          {!collapsed && (
            <span className="truncate text-muted-foreground">
              {status === "online" ? "后端已连接" : status === "connecting" ? "正在连接后端" : "后端未连接"}
            </span>
          )}
        </div>

        <div className={cn("mt-1 flex items-center gap-1", collapsed && "flex-col")}>
          <button
            type="button"
            onClick={toggleTheme}
            title={theme === "dark" ? "切换到浅色主题" : "切换到深色主题"}
            className="flex h-8 flex-1 items-center justify-center gap-1.5 rounded-md text-xs text-muted-foreground transition-colors hover:bg-sidebar-accent hover:text-foreground"
          >
            {theme === "dark" ? <Sun className="size-3.5" /> : <Moon className="size-3.5" />}
            {!collapsed && <span>主题</span>}
          </button>
          <button
            type="button"
            onClick={toggle}
            title={collapsed ? "展开侧栏" : "收起侧栏"}
            className="flex h-8 flex-1 items-center justify-center gap-1.5 rounded-md text-xs text-muted-foreground transition-colors hover:bg-sidebar-accent hover:text-foreground"
          >
            {collapsed ? <ChevronsRight className="size-3.5" /> : <ChevronsLeft className="size-3.5" />}
            {!collapsed && <span>收起</span>}
          </button>
        </div>
      </div>
    </aside>
  );
}

export function SidebarBadge() {
  return (
    <span className="inline-flex items-center gap-1 rounded-full border border-primary/30 bg-primary/10 px-2 py-0.5 text-[10px] font-medium text-primary">
      <Sparkles className="size-3" />
      V1.0
    </span>
  );
}