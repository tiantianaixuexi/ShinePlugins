import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import {
  ArrowLeft,
  BookOpen,
  Boxes,
  Calendar,
  CircleAlert,
  FileText,
  Pencil,
  Settings2,
  Trash2,
  User,
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
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { useDeleteProject, useProject } from "@/hooks/use-projects";
import { errorMessage } from "@/lib/api";
import { cn, formatNumber, formatRelativeTime, percent } from "@/lib/utils";

import { ProjectEditDialog } from "./project-edit-dialog";

function Stat({
  label,
  value,
  icon: Icon,
}: {
  label: string;
  value: string;
  icon: typeof BookOpen;
}) {
  return (
    <div className="rounded-lg border bg-card p-3">
      <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
        <Icon className="size-3" />
        {label}
      </div>
      <div className="mt-1 text-lg font-semibold tabular-nums">{value}</div>
    </div>
  );
}

export function ProjectDetailPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();
  const query = useProject(projectId);
  const deleteProject = useDeleteProject();
  const [editing, setEditing] = useState(false);
  const [confirming, setConfirming] = useState(false);

  const project = query.data;

  const handleDelete = async () => {
    if (!projectId) return;
    try {
      await deleteProject.mutateAsync({ id: projectId, hard: false });
      toast.success("项目已移除");
      navigate("/projects");
    } catch (error) {
      toast.error("删除失败", { description: errorMessage(error) });
    }
  };

  if (query.isPending) {
    return (
      <div className="mx-auto w-full max-w-4xl space-y-4 p-6">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-40" />
        <div className="grid gap-3 sm:grid-cols-3">
          {Array.from({ length: 3 }).map((_, index) => (
            <Skeleton key={index} className="h-24" />
          ))}
        </div>
      </div>
    );
  }

  if (query.isError || !project) {
    return (
      <div className="mx-auto w-full max-w-2xl p-6">
        <Card className="border-destructive/40">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base text-destructive">
              <CircleAlert className="size-4" />
              无法打开项目
            </CardTitle>
            <CardDescription>{errorMessage(query.error)}</CardDescription>
          </CardHeader>
          <CardContent>
            <Button asChild variant="outline" size="sm">
              <Link to="/projects">返回项目列表</Link>
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  const progress = percent(project.stats.words, project.target_word_count);

  return (
    <div className="mx-auto w-full max-w-4xl space-y-6 p-6">
      <div className="flex items-center gap-2">
        <Button asChild variant="ghost" size="sm">
          <Link to="/projects">
            <ArrowLeft className="size-4" />
            项目列表
          </Link>
        </Button>
      </div>

      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <h2 className="truncate text-xl font-semibold tracking-tight">{project.name}</h2>
            <Badge variant="outline">{project.novel_type}</Badge>
            <Badge variant="muted">v{project.row_version}</Badge>
          </div>
          <p className="mt-1 text-xs text-muted-foreground">
            更新于 {formatRelativeTime(project.updated_at)} · {project.language}
            {project.author ? ` · ${project.author}` : ""}
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={() => setEditing(true)}>
            <Settings2 className="size-4" />
            设置
          </Button>
          <Button size="sm" asChild>
            <Link to={`/projects/${project.id}/editor`}>
              <BookOpen className="size-4" />
              开始创作
            </Link>
          </Button>
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        <Stat label="已写字数" value={formatNumber(project.stats.words)} icon={FileText} />
        <Stat label="章节数" value={formatNumber(project.stats.chapters)} icon={BookOpen} />
        <Stat label="人物" value={formatNumber(project.stats.characters)} icon={User} />
        <Stat label="大纲" value={formatNumber(project.stats.outlines)} icon={Boxes} />
        <Stat label="知识块" value={formatNumber(project.stats.chunks)} icon={Boxes} />
        <Stat label="版本快照" value={formatNumber(project.stats.versions)} icon={Calendar} />
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">创作进度</CardTitle>
          <CardDescription>
            目标 {formatNumber(project.target_word_count)} 字 ·{" "}
            {formatNumber(project.target_chapter_count)} 章
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span>{formatNumber(project.stats.words)} 字</span>
            <span>{progress}%</span>
          </div>
          <Progress value={progress} className="mt-2" />
        </CardContent>
      </Card>

      {project.synopsis && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">故事简介</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="whitespace-pre-wrap text-sm leading-relaxed text-muted-foreground">
              {project.synopsis}
            </p>
          </CardContent>
        </Card>
      )}

      <Card className="border-dashed">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Pencil className="size-4 text-muted-foreground" />
            项目路径
          </CardTitle>
          <CardDescription>数据库与素材都保存在这个目录中</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="truncate rounded-md border bg-muted/40 px-3 py-2 font-mono text-xs">
            {project.path}
          </div>
          <div className="flex items-center justify-between gap-3">
            <p className="text-xs text-muted-foreground">
              删除只会从列表移除，磁盘目录会保留。
            </p>
            <div className="flex gap-2">
              {confirming ? (
                <>
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
                </>
              ) : (
                <Button size="sm" variant="outline" onClick={() => setConfirming(true)}>
                  <Trash2 className="size-4" />
                  删除项目
                </Button>
              )}
            </div>
          </div>
        </CardContent>
      </Card>

      <ProjectEditDialog project={project} open={editing} onOpenChange={setEditing} />

      <p className={cn("text-center text-[11px] text-muted-foreground")}>
        数据结构版本 v{project.schema_version} · 行版本 {project.row_version}
      </p>
    </div>
  );
}