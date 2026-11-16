import { useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import {
  AlertTriangle,
  BookOpen,
  Copy,
  FolderOpen,
  MoreHorizontal,
  Plus,
  RefreshCw,
  Trash2,
  Users,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { useDeleteProject, useDuplicateProject, useProjects } from "@/hooks/use-projects";
import { errorMessage } from "@/lib/api";
import { cn, formatNumber, formatRelativeTime, percent } from "@/lib/utils";
import type { ProjectSummary } from "@/types/api";

import { ProjectFormDialog } from "./project-form-dialog";

const TYPE_VARIANT: Record<string, "default" | "secondary" | "outline" | "muted"> = {
  玄幻: "default",
  都市: "secondary",
  科幻: "secondary",
  悬疑: "outline",
  言情: "outline",
  历史: "muted",
  武侠: "muted",
};

function ProjectCard({ project }: { project: ProjectSummary }) {
  const deleteProject = useDeleteProject();
  const duplicateProject = useDuplicateProject();
  const [confirming, setConfirming] = useState(false);

  const handleDuplicate = async () => {
    try {
      await duplicateProject.mutateAsync({
        id: project.id,
        name: `${project.name} 副本`,
      });
      toast.success("已创建副本");
    } catch (error) {
      toast.error("复制失败", { description: errorMessage(error) });
    }
  };

  const handleDelete = async () => {
    try {
      await deleteProject.mutateAsync({ id: project.id, hard: false });
      toast.success(`已移除《${project.name}》（可恢复的项目目录仍在磁盘上）`);
    } catch (error) {
      toast.error("删除失败", { description: errorMessage(error) });
    } finally {
      setConfirming(false);
    }
  };

  return (
    <Card className="group relative gap-4 py-4 transition-colors hover:border-primary/40">
      <CardHeader className="px-4">
        <div className="flex items-start gap-2">
          <div className="min-w-0 flex-1">
            <CardTitle className="truncate text-base">
              <Link to={`/projects/${project.id}`} className="hover:text-primary">
                {project.name}
              </Link>
            </CardTitle>
            <CardDescription className="mt-1 text-xs">
              更新于 {formatRelativeTime(project.updated_at)}
            </CardDescription>
          </div>
          <div className="flex shrink-0 items-center gap-1">
            <Badge variant={TYPE_VARIANT[project.novel_type] ?? "outline"}>
              {project.novel_type}
            </Badge>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  className="opacity-60 transition-opacity group-hover:opacity-100"
                >
                  <MoreHorizontal className="size-4" />
                  <span className="sr-only">项目操作</span>
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-40">
                <DropdownMenuItem asChild>
                  <Link to={`/projects/${project.id}`}>
                    <FolderOpen className="size-4" />
                    打开项目
                  </Link>
                </DropdownMenuItem>
                <DropdownMenuItem onClick={() => void handleDuplicate()}>
                  <Copy className="size-4" />
                  复制项目
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem
                  variant="destructive"
                  onClick={() => setConfirming(true)}
                >
                  <Trash2 className="size-4" />
                  删除项目
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </div>
      </CardHeader>
      <CardContent className="px-4">
        <div className="flex items-center justify-between text-xs text-muted-foreground">
          <span className="inline-flex items-center gap-1">
            <BookOpen className="size-3" />
            {formatNumber(project.target_word_count)} 字目标
          </span>
          <span>{formatNumber(project.target_chapter_count)} 章</span>
        </div>
        <Progress
          className="mt-2 h-1"
          value={percent(0, project.target_word_count)}
        />
      </CardContent>

      {confirming && (
        <div className="absolute inset-0 z-10 flex flex-col items-center justify-center gap-2 rounded-xl bg-card/95 p-4 text-center backdrop-blur">
          <AlertTriangle className="size-5 text-destructive" />
          <p className="text-sm font-medium">删除《{project.name}》？</p>
          <p className="text-xs text-muted-foreground">
            项目会从列表中移除，磁盘目录仍会保留。
          </p>
          <div className="mt-1 flex gap-2">
            <Button size="sm" variant="outline" onClick={() => setConfirming(false)}>
              取消
            </Button>
            <Button
              size="sm"
              variant="destructive"
              disabled={deleteProject.isPending}
              onClick={() => void handleDelete()}
            >
              确认删除
            </Button>
          </div>
        </div>
      )}
    </Card>
  );
}

export function ProjectsPage() {
  const { data, isLoading, isError, error, refetch, isFetching } = useProjects();
  const [createOpen, setCreateOpen] = useState(false);

  return (
    <div className="mx-auto w-full max-w-6xl p-6">
      <div className="mb-6 flex items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold tracking-tight">小说项目</h2>
          <p className="text-sm text-muted-foreground">
            每个项目拥有独立的目录、数据库与索引，互不干扰。
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => void refetch()} disabled={isFetching}>
            <RefreshCw className={cn("size-4", isFetching && "animate-spin")} />
            刷新
          </Button>
          <Button size="sm" onClick={() => setCreateOpen(true)}>
            <Plus className="size-4" />
            新建项目
          </Button>
        </div>
      </div>

      {isLoading && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 3 }).map((_, index) => (
            <Skeleton key={index} className="h-32 rounded-xl" />
          ))}
        </div>
      )}

      {isError && (
        <Card className="border-destructive/40">
          <CardHeader>
            <CardTitle className="text-base text-destructive">无法连接后端服务</CardTitle>
            <CardDescription>{errorMessage(error)}</CardDescription>
          </CardHeader>
          <CardContent>
            <Button variant="outline" size="sm" onClick={() => void refetch()}>
              重试
            </Button>
          </CardContent>
        </Card>
      )}

      {!isLoading && !isError && (data?.length ?? 0) === 0 && (
        <Card className="studio-grid">
          <CardContent className="flex flex-col items-center gap-3 py-16 text-center">
            <div className="grid size-12 place-items-center rounded-xl border bg-background">
              <BookOpen className="size-5 text-muted-foreground" />
            </div>
            <div>
              <p className="font-medium">还没有小说项目</p>
              <p className="text-sm text-muted-foreground">
                创建一个项目，开始规划你的长篇故事。
              </p>
            </div>
            <Button size="sm" onClick={() => setCreateOpen(true)}>
              <Plus className="size-4" />
              新建项目
            </Button>
          </CardContent>
        </Card>
      )}

      {!isLoading && !isError && (data?.length ?? 0) > 0 && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {data?.map((project) => (
            <ProjectCard key={project.id} project={project} />
          ))}
        </div>
      )}

      <ProjectFormDialog open={createOpen} onOpenChange={setCreateOpen} />
    </div>
  );
}

export function ProjectTypeIcon() {
  return <Users className="size-4" />;
}