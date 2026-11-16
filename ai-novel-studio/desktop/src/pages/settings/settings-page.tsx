import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { ModelConfigPanel } from "@/components/settings/model-config-panel";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { useBackendHealth, useStudioStats, useSystemInfo } from "@/hooks/use-backend";
import { useTheme } from "@/hooks/use-theme";
import { Moon, Sun } from "lucide-react";

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4 py-2 text-sm">
      <span className="shrink-0 text-muted-foreground">{label}</span>
      <span className="min-w-0 truncate text-right">{value}</span>
    </div>
  );
}

export function SettingsPage() {
  const info = useSystemInfo();
  const health = useBackendHealth();
  const stats = useStudioStats();
  const { theme, setTheme } = useTheme();

  return (
    <div className="mx-auto w-full max-w-4xl space-y-6 p-6">
      <div>
        <h2 className="text-lg font-semibold tracking-tight">系统设置</h2>
        <p className="text-sm text-muted-foreground">
          模型配置、存储位置与诊断信息。所有数据都保存在本机。
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">运行环境</CardTitle>
          <CardDescription>桌面端与 Python 后端的连接状态</CardDescription>
        </CardHeader>
        <CardContent className="divide-y">
          {info.isPending ? (
            <Skeleton className="h-32" />
          ) : (
            <>
              <Row
                label="后端服务"
                value={
                  <Badge
                    variant={
                      health.status === "online"
                        ? "success"
                        : health.status === "connecting"
                          ? "warning"
                          : "destructive"
                    }
                  >
                    {health.status === "online"
                      ? "在线"
                      : health.status === "connecting"
                        ? "连接中"
                        : "离线"}
                  </Badge>
                }
              />
              <Row label="应用版本" value={info.data?.version ?? "—"} />
              <Row label="运行环境" value={info.data?.environment ?? "—"} />
              <Row label="数据结构版本" value={`v${info.data?.schema_version ?? "—"}`} />
              <Row label="已注册项目" value={stats.data?.totals.projects ?? "—"} />
              <Row
                label="数据目录"
                value={
                  <span className="font-mono text-xs" title={info.data?.data_dir}>
                    {info.data?.data_dir ?? "—"}
                  </span>
                }
              />
              <Row
                label="项目目录"
                value={
                  <span className="font-mono text-xs" title={info.data?.projects_dir}>
                    {info.data?.projects_dir ?? "—"}
                  </span>
                }
              />
            </>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">模型配置</CardTitle>
          <CardDescription>LLM 端点、能力画像与密钥管理</CardDescription>
        </CardHeader>
        <CardContent>
          <ModelConfigPanel />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">外观</CardTitle>
          <CardDescription>界面主题会立即应用并记住选择</CardDescription>
        </CardHeader>
        <CardContent className="flex gap-2">
          <Button
            variant={theme === "light" ? "default" : "outline"}
            size="sm"
            onClick={() => setTheme("light")}
          >
            <Sun className="size-4" />
            浅色
          </Button>
          <Button
            variant={theme === "dark" ? "default" : "outline"}
            size="sm"
            onClick={() => setTheme("dark")}
          >
            <Moon className="size-4" />
            深色
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">关于</CardTitle>
          <CardDescription>AI Novel Studio · 长篇小说创作与影视化生产平台</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3 text-sm text-muted-foreground">
          <Separator />
          <p>
            当前为 <strong className="text-foreground">V1.0</strong> 阶段：桌面框架、项目管理、
            小说编辑与长篇记忆。故事板与工作流在 V1.5 交付，AI 影视化生产在 V2.0 交付。
          </p>
          <p className="text-xs">
            日志位置：<span className="font-mono">{info.data?.data_dir ?? "—"}/logs/backend.log</span>
          </p>
        </CardContent>
      </Card>
    </div>
  );
}