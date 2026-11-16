import { Link } from "react-router-dom";
import {
  ArrowRight,
  BookOpen,
  Boxes,
  CircleCheck,
  CircleDashed,
  FileText,
  Plus,
  Sparkles,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { NAV_ITEMS } from "@/config/navigation";
import { useBackendHealth, useStudioStats, useSystemInfo } from "@/hooks/use-backend";
import { cn, formatCompact, formatNumber, formatRelativeTime } from "@/lib/utils";

function greeting(): string {
  const hour = new Date().getHours();
  if (hour < 6) return "夜深了";
  if (hour < 11) return "早上好";
  if (hour < 14) return "中午好";
  if (hour < 18) return "下午好";
  return "晚上好";
}

function StatCard({
  label,
  value,
  hint,
  icon: Icon,
}: {
  label: string;
  value: string;
  hint: string;
  icon: typeof BookOpen;
}) {
  return (
    <Card className="gap-3 py-4">
      <CardContent className="px-4">
        <div className="flex items-center justify-between text-xs text-muted-foreground">
          <span>{label}</span>
          <Icon className="size-3.5" />
        </div>
        <div className="mt-2 text-2xl font-semibold tracking-tight tabular-nums">{value}</div>
        <div className="mt-0.5 text-[11px] text-muted-foreground">{hint}</div>
      </CardContent>
    </Card>
  );
}

export function DashboardPage() {
  const stats = useStudioStats();
  const health = useBackendHealth();
  const info = useSystemInfo();

  const totals = stats.data?.totals;
  const projects = stats.data?.projects ?? [];
  const latest = projects[0];

  const pipeline = NAV_ITEMS.filter((item) => item.path !== "/settings");

  return (
    <div className="mx-auto w-full max-w-6xl space-y-6 p-6">
      {/* Hero */}
      <Card className="studio-grid relative overflow-hidden">
        <CardContent className="flex flex-col gap-5 py-8 sm:flex-row sm:items-center sm:justify-between">
          <div className="space-y-1.5">
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <Sparkles className="size-3.5 text-primary" />
              AI 长篇小说创作工作站
            </div>
            <h2 className="text-2xl font-semibold tracking-tight">
              {greeting()}，今天想写点什么？
            </h2>
            <p className="max-w-lg text-sm text-muted-foreground">
              规划故事、持续创作、自动维护长篇记忆，最后把小说变成剧本与成片。
            </p>
          </div>
          <div className="flex shrink-0 flex-wrap gap-2">
            {latest && (
              <Button asChild variant="outline" size="sm">
                <Link to={`/projects/${latest.id}`}>
                  <BookOpen className="size-4" />
                  继续《{latest.name.length > 10 ? `${latest.name.slice(0, 10)}…` : latest.name}》
                </Link>
              </Button>
            )}
            <Button asChild size="sm">
              <Link to="/projects">
                <Plus className="size-4" />
                新建小说
              </Link>
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Counters */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {stats.isPending ? (
          Array.from({ length: 4 }).map((_, index) => <Skeleton key={index} className="h-24" />)
        ) : (
          <>
            <StatCard
              label="项目"
              value={formatNumber(totals?.projects ?? 0)}
              hint="本地项目总数"
              icon={Boxes}
            />
            <StatCard
              label="累计字数"
              value={formatCompact(totals?.words ?? 0)}
              hint={`${formatNumber(totals?.words ?? 0)} 字`}
              icon={FileText}
            />
            <StatCard
              label="章节"
              value={formatNumber(totals?.chapters ?? 0)}
              hint="已保存的章节数"
              icon={BookOpen}
            />
            <StatCard
              label="人物 / 知识块"
              value={`${formatNumber(totals?.characters ?? 0)} / ${formatCompact(totals?.chunks ?? 0)}`}
              hint="人物与可检索知识块"
              icon={CircleDashed}
            />
          </>
        )}
      </div>

      <div className="grid gap-6 lg:grid-cols-[1.6fr_1fr]">
        {/* Recent projects */}
        <Card>
          <CardHeader className="flex-row items-center justify-between space-y-0">
            <div>
              <CardTitle className="text-base">最近项目</CardTitle>
              <CardDescription>按最后更新时间排序</CardDescription>
            </div>
            <Button asChild variant="ghost" size="sm">
              <Link to="/projects">
                全部
                <ArrowRight className="size-4" />
              </Link>
            </Button>
          </CardHeader>
          <CardContent className="flex flex-col gap-2">
            {stats.isPending && <Skeleton className="h-24" />}
            {!stats.isPending && projects.length === 0 && (
              <div className="flex flex-col items-center gap-2 py-8 text-center text-sm text-muted-foreground">
                <BookOpen className="size-5" />
                还没有项目，创建第一部小说吧。
              </div>
            )}
            {projects.slice(0, 5).map((project) => (
              <Link
                key={project.id}
                to={`/projects/${project.id}`}
                className="flex items-center gap-3 rounded-lg border border-transparent px-3 py-2.5 transition-colors hover:border-border hover:bg-muted/40"
              >
                <div className="grid size-8 shrink-0 place-items-center rounded-md bg-primary/10">
                  <BookOpen className="size-4 text-primary" />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm font-medium">{project.name}</div>
                  <div className="text-xs text-muted-foreground">
                    {formatNumber(project.words)} 字 · {formatNumber(project.chapters)} 章
                  </div>
                </div>
                <div className="shrink-0 text-right text-[11px] text-muted-foreground">
                  {formatRelativeTime(project.updated_at)}
                </div>
              </Link>
            ))}
          </CardContent>
        </Card>

        {/* Backend status */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">运行状态</CardTitle>
            <CardDescription>本地后端与存储</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground">后端服务</span>
              <Badge variant={health.status === "online" ? "success" : health.status === "connecting" ? "warning" : "destructive"}>
                {health.status === "online" ? "在线" : health.status === "connecting" ? "连接中" : "离线"}
              </Badge>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground">版本</span>
              <span className="tabular-nums">{info.data?.version ?? "—"}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground">数据结构版本</span>
              <span className="tabular-nums">v{info.data?.schema_version ?? "—"}</span>
            </div>
            <div className="min-w-0">
              <div className="text-muted-foreground">数据目录</div>
              <div className="truncate font-mono text-[11px]" title={info.data?.data_dir}>
                {info.data?.data_dir ?? "—"}
              </div>
            </div>
            <div className="min-w-0">
              <div className="text-muted-foreground">项目目录</div>
              <div className="truncate font-mono text-[11px]" title={info.data?.projects_dir}>
                {info.data?.projects_dir ?? "—"}
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Pipeline */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">创作流水线</CardTitle>
          <CardDescription>从灵感到成片，模块按里程碑交付</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
            {pipeline.map((item, index) => {
              const Icon = item.icon;
              return (
                <Link
                  key={item.path}
                  to={item.path}
                  className={cn(
                    "flex items-start gap-3 rounded-lg border p-3 transition-colors hover:bg-muted/40",
                    item.implemented ? "border-border" : "border-dashed",
                  )}
                >
                  <div className="mt-0.5 grid size-7 shrink-0 place-items-center rounded-md bg-muted">
                    <Icon className="size-3.5 text-muted-foreground" />
                  </div>
                  <div className="min-w-0">
                    <div className="flex items-center gap-1.5">
                      <span className="truncate text-sm font-medium">{item.label}</span>
                      {item.implemented ? (
                        <CircleCheck className="size-3.5 shrink-0 text-emerald-500" />
                      ) : (
                        <span className="shrink-0 text-[10px] text-muted-foreground">
                          {item.milestone}
                        </span>
                      )}
                    </div>
                    <div className="mt-0.5 line-clamp-2 text-[11px] text-muted-foreground">
                      {item.description}
                    </div>
                    <div className="mt-1 text-[10px] text-muted-foreground/70">
                      步骤 {index + 1}
                    </div>
                  </div>
                </Link>
              );
            })}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}